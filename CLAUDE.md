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

### Data model: `Album.is_active`, not a foreign key

Which photos are "on screen" is driven by `Album.is_active` (boolean on each album), not a single
`Settings.active_album_id`. Multiple albums can be active at once. If **no** album is active,
`/display` falls back to showing the entire photo library. This fallback logic lives in
`app/routers/display_router.py::_active_photos()` — any change to album/photo selection needs to
preserve that fallback or the display goes blank.

### Photos are stored as three JPEG variants

`app/image_utils.py::save_upload()` normalizes every upload (EXIF orientation fix, non-JPEG →
JPEG) and writes three sibling files sharing one UUID filename under `data/photos/{original,display,thumb}/`.
Deleting a photo (`delete_photo_files()`) must remove all three.

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

`Base.metadata.create_all()` on startup is the only migration mechanism. A schema change is applied
by deleting `data/db/photoframe.db` and letting it recreate — acceptable for a single-user hobby
deployment, but worth knowing before assuming migrations exist.

### Pinned dependency quirk

`requirements.txt` pins `sqlalchemy==2.0.52`, not an earlier 2.0.x — earlier versions (e.g. 2.0.36)
fail at import time on Python 3.14 when resolving `Mapped[float | None]`-style column annotations in
`app/models.py`. If bumping SQLAlchemy or the Python version, re-check this.
