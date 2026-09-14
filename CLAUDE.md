# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A digital photo frame for a Raspberry Pi hooked to a screen. A single FastAPI service serves both
the admin panel (upload/organize photos, configure the slideshow) and the JSON API that the kiosk
display page polls. See `README.md` for the user-facing quickstart and `kiosk-setup/README.md` for
the Raspberry Pi kiosk setup.

## Commands

```bash
# Local dev setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env

# Run the dev server (reads .env)
uvicorn app.main:app --reload --port 8080

# Tests
pytest                                              # full suite
pytest tests/test_smoke.py -v                       # one file
pytest tests/test_smoke.py::test_settings_roundtrip -v   # one test
pytest tests/test_schedule.py -v                    # pure-function schedule tests, no app/DB needed

# Docker (this is what actually ships)
docker compose up -d --build
docker compose logs -f
docker compose down
```

There is no linter/formatter configured in this repo (no ruff/black/flake8 config) — don't assume one.

## Architecture

### The Docker/host split is the central design decision

Docker runs **only** the FastAPI backend (`docker-compose.yml` has a single `photoframe` service,
bind-mounting `./data`). The Chromium kiosk browser and the screen on/off scheduler run **outside**
Docker, directly on the Pi host, via `kiosk-setup/` (autostart `.desktop` entry + a `systemd --user`
service). This is because passing X11/Wayland through to a container on Raspberry Pi is fragile.
Don't try to "fix" this by containerizing the kiosk browser — it's intentional. `kiosk-setup/*.sh`
only ever talks to the backend over `http://localhost:$PORT`, never touches the container directly.

### Auth: no users, just an invite code

`app/auth.py` implements a single-secret scheme (`INVITE_CODE` env var, no username/password).
`require_admin` (a FastAPI dependency applied at the router level in `admin_router.py`) doesn't
raise `HTTPException` — it raises the custom `AdminAuthRequired`, caught by an exception handler in
`app/main.py` that returns `HX-Redirect: /login` for HTMX requests and a normal 303 redirect
otherwise. New protected admin routes just need `dependencies=[Depends(require_admin)]` on their
router; no per-route auth code needed. Sessions are signed cookies (`itsdangerous`, 1-year max-age,
no server-side session store) — "logging in" just means holding a valid signed cookie.

### Data model: every photo belongs to exactly one album

`Photo.album_id` is a required FK (one-to-many, not the many-to-many `album_photos` table this used
to be). A photo can't exist without an album; "moving" a photo between albums is just reassigning
`album_id` (`PATCH /admin/photos/{id}/album` in `app/routers/admin_router.py`). Deleting a local
album requires it to be empty first (move or delete its photos) — there's no longer an "orphan
bucket" to fall back into, so the delete endpoint blocks with an error instead of silently
cascading.

Which photos are "on screen" is still driven by `Album.is_active` (boolean on each album, multiple
albums can be active at once). If **no** album is active, `/display` falls back to showing the
entire photo library — this fallback logic lives in `app/routers/display_router.py::_active_photos()`
and must be preserved or the display goes blank. On top of that, a photo is excluded from "active"
if its album is tied to a currently-disconnected USB volume (`Album.connected`) — *unless* the photo
already has a local copy (`Photo.has_original`), since the whole point of "copiar a la biblioteca"
is that it survives the drive being unplugged. See the USB section below.

`/admin/photos` (the "Fotos" tab) reuses this exact same `_active_photos()` query — it shows what's
actually on the display right now, not every photo ever uploaded. Uploading requires picking an
album first (`album_id` is a required form field on `POST /admin/photos`); there's no more
album-less generic upload — the upload form lives on each album's own detail page.

### Photos are stored as three JPEG variants (usually)

`app/image_utils.py::save_upload()` normalizes every upload (EXIF orientation fix, non-JPEG →
JPEG) and writes three sibling files sharing one UUID filename under `data/photos/{original,display,thumb}/`.
Deleting a photo (`delete_photo_files()`) must remove all three (`missing_ok=True`, safe even if one
never existed).

Photos registered from a USB drive (`Photo.source == "usb"`) are the exception: until the user
copies them to the library, only `display`+`thumb` exist (`Photo.has_original = False`) — see the
USB section below. `save_upload`/`save_variants`/`promote_to_original` all share the same
normalize-then-write-selected-subdirs logic in `image_utils.py`; if you touch the resize/quality
constants (`DISPLAY_MAX`, `THUMB_MAX`, `JPEG_QUALITY`), it affects all three call sites.

Known limitation: the image-file filter (used both by the admin upload's `accept` attribute and the
USB daemon's folder scan) doesn't include `.heic`/`.heif` (the default format for iPhone photos),
and Pillow can't decode those without the separate `pillow-heif` plugin, which isn't installed.

### `/display` is a polling client, not push-based

`static/js/display.js` polls `GET /api/display/state` every ~10s and compares `photos_version`
(hash of the current photo id list) and `settings_version` (`Settings.updated_at`) against what it
last saw to decide whether to re-render photos or re-apply settings (transition, fit, orientation,
overlays). There's no WebSocket/SSE — if you add a field to `Settings` or `/api/display/state`,
`display.js` needs a matching read, and bumping `updated_at` is what makes it propagate.

### Screen schedule has one source of truth, two consumers

`app/schedule.py::compute_screen_on(schedule_enabled, on_time, off_time, now)` is the only place
that decides whether the screen should be on, including midnight-wraparound windows (e.g.
off=22:00 → on=07:00). It's consumed by:
1. `GET /api/display/screen-status` → `static/js/display.js`, which blacks out the page in-browser
   (works with zero host setup, testable without real hardware).
2. `kiosk-setup/screen-schedule.sh`, a host-side loop (outside Docker) that polls the same endpoint
   and calls `vcgencmd display_power 0/1` to actually cut the HDMI signal — real power savings, but
   only verifiable on real Raspberry Pi hardware (`vcgencmd` doesn't exist elsewhere).

On the same state change, `screen-schedule.sh` also calls `sudo kiosk-setup/cpu-throttle-apply.sh
low|normal` to drop the CPU governor to `powersave` (capped at the hardware's min frequency) during
off-hours. There is no way to fully power off the SoC and have it wake itself on a schedule — no
RTC wake-alarm on stock Pi hardware, no reliable suspend-to-RAM — so this is the software-only
ceiling; true near-zero consumption would need external hardware (a scheduled smart plug) cutting
supply power, which is out of scope here. `cpu-throttle-apply.sh` saves each CPU core's *current*
governor to `/run/photoframe-cpu-governor.orig` before switching to `powersave`, and restores the
exact saved value on `normal` — it deliberately does not hardcode a governor name to restore to,
since the RPi OS default varies by kernel version (`ondemand` vs `schedutil`).

### Privileged actions (shutdown/reboot/hide) use a one-shot pending-action queue

The touch menu on `/display` (3 taps in the top-left corner) needs to run `shutdown`/`reboot`,
which the container can't do either — same Docker/host boundary as the screen schedule, but here
the trigger direction is reversed (browser → backend → host, instead of host polling a
schedule computed from settings). `app/power.py` holds a single in-memory pending action
(`request_action()` / `consume_pending_action()`, guarded by a `threading.Lock`, fine only because
the app runs as a single uvicorn process/worker — don't add `--workers` without rethinking this).
`POST /api/display/power-action` sets it; `GET /api/display/power-status` returns-and-clears it
(one-shot, so `kiosk-setup/power-listener.sh` polling every 2s doesn't re-trigger the same action).
For `shutdown`/`reboot`, the listener runs `sudo shutdown`/`sudo reboot`, enabled by a
sudoers rule installed by `install.sh` (`/etc/sudoers.d/photoframe-power`, scoped to exactly those
two commands — never broaden it). For `hide` (temporarily close the kiosk browser without
stranding a touch-only device with no way back in), the listener kills Chromium and writes a
timestamp to `/tmp/photoframe-kiosk-suppress-until`; `kiosk-setup/kiosk.sh`'s relaunch loop checks
that file before its normal 5-second auto-relaunch and sleeps until the timestamp instead. Neither
`power-action` nor `power-status` requires the invite-code auth — same trust boundary as the rest
of `/display` (LAN-only, and physical access to the touchscreen already means physical access to
the Pi's power cable).

### USB auto-import creates temporary albums, never copies originals up front

`kiosk-setup/usb-import.py` (optional, installed separately via `install-usb-import.sh`, not part
of the main `install.sh`) is a fourth instance of the Docker/host boundary: Docker can't see USB
drives the desktop mounts after the container started. Unlike the old `usb-import.sh` (which
uploaded every photo immediately), this daemon polls every 15s and sends the backend a lightweight
JSON "heartbeat" — which USB volumes are connected (identified by filesystem UUID via
`findmnt`+`blkid`, never the OS-assigned volume label, which isn't stable or unique across
devices) and which image files exist in which folders, metadata only, no bytes. `POST
/admin/usb/heartbeat` in `app/routers/usb_router.py` upserts a `UsbVolume` row per drive, creates
one `Album` per photo-containing folder the first time it's seen (matched afterwards by
`(usb_volume_id, source_relpath)`, active immediately), and tells the daemon which files still need
uploading and which photos have a pending "copy to library" request.

The daemon then uploads each new/changed file to `POST /admin/usb/photos`, which generates only
`display`+`thumb` variants (`image_utils.save_variants(..., subdirs=("display", "thumb"))`) and
**never writes an "original"** — `Photo.has_original` stays `False`. The original bytes are
discarded after generating those two derivatives; only when the user explicitly clicks "copiar a la
biblioteca" (single photo or whole album, from the album's detail page) does the flow continue: the
backend marks `Photo.copy_requested_at`, the next heartbeat tells the daemon to re-read the real
file from the still-connected drive, and it POSTs the actual bytes to
`/admin/usb/photos/{id}/copy-complete`, which runs the full original+display+thumb pipeline and
flips `has_original=True`. If the drive gets unplugged before that happens, the request just waits
— no timeout, matching the one-shot pending-action style already used in `app/power.py`, except
this one is durable (stored as DB columns, not in-memory) since it has to survive a container
restart while waiting for the drive to come back.

Dedup is server-side now (by `(album_id, source_relpath)`, refreshed if `source_size`/`source_mtime`
change) instead of the old host-side `sha256sum` file — the daemon carries no local state beyond the
session cookie jar. **Non-obvious gotcha, still applies**: `AdminAuthRequired` responds with a 303
redirect (not 4xx) for non-HTMX requests, so checking success via a redirect-following HTTP client
silently lies — the daemon's `_NoRedirect` handler in `usb-import.py` (a stdlib `urllib` opener that
refuses to follow redirects) exists specifically so `login()` can see the real 303/401 status code
instead of whatever the followed redirect's page returns. If you add more host scripts that call
authenticated endpoints, replicate that pattern, not a redirect-following client.

### Environment settings are read at import time

`app/config.py` instantiates `settings = Settings()` (pydantic-settings) at module import time and
eagerly creates the `data/` subdirectories right there — this happens before FastAPI's `lifespan`
runs, because `app/main.py` calls `StaticFiles(directory=...)` at import time too and that raises if
the directory doesn't exist yet. Table creation (`Base.metadata.create_all`) does still happen in
`lifespan`, not at import time. Because of this ordering, `tests/conftest.py` sets `DATA_DIR`,
`INVITE_CODE`, `SECRET_KEY` as env vars at **module level** (before `from app.main import app`), not
inside a fixture — fixtures run too late, after collection-time imports already happened. Tests use
`with TestClient(app) as c:` specifically to trigger the lifespan context.

### No Alembic

`Base.metadata.create_all()` on startup is the default migration mechanism — for a brand new
install, deleting `data/db/photoframe.db` and letting it recreate is still the way to apply a
schema change, and still acceptable for a single-user hobby deployment.

The one exception is `app/migrations.py::migrate_legacy_schema()`, called from `main.py`'s
`lifespan` **before** `create_all()` (order matters: `create_all()` never alters an existing table).
It's a guarded, one-time raw-`sqlite3` migration (deliberately not going through the SQLAlchemy
engine/pool — rebuilding `albums` to drop a `UNIQUE` constraint needs `PRAGMA foreign_keys=OFF`,
and leaving that pragma flipped on a pooled connection the app reuses later would silently disable
referential integrity checking for the rest of the process's life) that detects the pre-single-album
schema (absence of `photos.album_id`), backs up the `.db` file first, then backfills every photo
into a real album and drops the old `album_photos` table. If you need another structural change
that can't be expressed as a fresh `create_all()`, follow this same shape: raw connection, own
transaction, backup before mutating, guarded by checking for the post-migration state so it only
ever runs once.

### Pinned dependency quirk

`requirements.txt` pins `sqlalchemy==2.0.52`, not an earlier 2.0.x — earlier versions (e.g. 2.0.36)
fail at import time on Python 3.14 when resolving `Mapped[float | None]`-style column annotations in
`app/models.py`. If bumping SQLAlchemy or the Python version, re-check this.
