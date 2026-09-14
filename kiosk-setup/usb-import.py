#!/usr/bin/env python3
"""Daemon de auto-detección de USB para el portarretrato.

Corre en el host, no en Docker: el contenedor no ve unidades que el
escritorio monta dinámicamente después de que arrancó (mismo motivo que el
resto de kiosk-setup/ -- ver CLAUDE.md).

Cada ~15s escanea /media y /mnt buscando carpetas de fotos en unidades
montadas, identifica cada unidad por el UUID de su filesystem (`blkid`, no el
label, que no es estable ni único entre dispositivos) y le manda al backend
un "heartbeat" liviano: solo metadata (qué unidades/carpetas/archivos hay),
nunca bytes. El backend responde qué archivos todavía no registró (para
subirlos a /admin/usb/photos, generando solo una vista previa -- nunca copia
el original) y qué fotos tienen un pedido de "copiar a la biblioteca"
pendiente (para releer el archivo real del disco y mandarlo a
/admin/usb/photos/{id}/copy-complete). El dashboard decide qué copiar; este
script nunca copia nada por su cuenta.

Reescribe el `usb-import.sh` anterior (que subía cada foto directo, como una
subida manual). Se eligió Python3 de la librería estándar en vez de bash +
jq para construir/parsear el JSON del heartbeat sin agregar una dependencia
nueva al host (python3 ya es un requisito del proyecto).
"""
import http.client
import http.cookiejar
import json
import mimetypes
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid as uuidlib
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
ENV_FILE = REPO_ROOT / ".env"

STATE_DIR = Path.home() / ".local/state/photoframe"
STATE_DIR.mkdir(parents=True, exist_ok=True)
COOKIE_FILE = STATE_DIR / "session-cookie.txt"

POLL_SECONDS = 15
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def read_env_var(name: str, default: str) -> str:
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith(f"{name}="):
                value = line.split("=", 1)[1].strip()
                if value:
                    return value
    return default


def base_url() -> str:
    return f"http://localhost:{read_env_var('PORT', '8080')}"


cookie_jar = http.cookiejar.MozillaCookieJar(str(COOKIE_FILE))
if COOKIE_FILE.exists():
    try:
        cookie_jar.load(ignore_discard=True, ignore_expires=True)
    except (OSError, http.cookiejar.LoadError):
        pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar), _NoRedirect())


def _status_and_body(req: urllib.request.Request) -> tuple[int, bytes]:
    # OJO: no asumir que 2xx == éxito por defecto de urllib -- /login y otros
    # endpoints de admin devuelven 303 (redirect a /login) cuando la sesión no
    # es válida, y si lo siguiéramos automáticamente terminaríamos "viendo" un
    # 200 en /login sin haber logueado nada (mismo gotcha ya documentado para
    # `curl -f` en el script anterior). _NoRedirect corta eso: acá siempre se
    # ve el código real.
    try:
        with opener.open(req, timeout=15) as resp:
            body = resp.read()
            cookie_jar.save(ignore_discard=True, ignore_expires=True)
            return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read()
        cookie_jar.save(ignore_discard=True, ignore_expires=True)
        return e.code, body
    except (urllib.error.URLError, http.client.HTTPException, OSError):
        return 0, b""


def login() -> bool:
    invite_code = read_env_var("INVITE_CODE", "")
    data = urllib.parse.urlencode({"code": invite_code}).encode()
    req = urllib.request.Request(f"{base_url()}/login", data=data, method="POST")
    status, _ = _status_and_body(req)
    return status == 303


def http_json(method: str, path: str, payload: dict) -> tuple[int, dict | None]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{base_url()}{path}", data=data, method=method, headers={"Content-Type": "application/json"}
    )
    status, body = _status_and_body(req)
    if status != 200:
        return status, None
    try:
        return status, json.loads(body)
    except json.JSONDecodeError:
        return status, None


def _encode_multipart(fields: dict, file_field: str, file_path: Path) -> tuple[str, bytes]:
    boundary = uuidlib.uuid4().hex
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    chunks.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
            f'filename="{file_path.name}"\r\nContent-Type: {content_type}\r\n\r\n'
        ).encode()
    )
    chunks.append(file_path.read_bytes())
    chunks.append(f"\r\n--{boundary}--\r\n".encode())
    return f"multipart/form-data; boundary={boundary}", b"".join(chunks)


def http_upload(path: str, fields: dict, file_path: Path) -> int:
    content_type, body = _encode_multipart(fields, "file", file_path)
    req = urllib.request.Request(
        f"{base_url()}{path}", data=body, method="POST", headers={"Content-Type": content_type}
    )
    status, _ = _status_and_body(req)
    return status


def find_mount_dirs() -> list[Path]:
    # /media/<usuario>/<VOLUMEN> es donde Raspberry Pi OS Desktop automonta USB.
    # /mnt/<algo> como respaldo por si el usuario montó algo manualmente ahí.
    dirs: list[Path] = []
    media = Path("/media")
    if media.is_dir():
        for user_dir in media.iterdir():
            if user_dir.is_dir():
                dirs.extend(p for p in user_dir.iterdir() if p.is_dir())
    mnt = Path("/mnt")
    if mnt.is_dir():
        dirs.extend(p for p in mnt.iterdir() if p.is_dir())
    return dirs


def resolve_fs_uuid(mount_dir: Path) -> str | None:
    try:
        device = subprocess.run(
            ["findmnt", "-no", "SOURCE", str(mount_dir)],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        if not device:
            return None
        fs_uuid = subprocess.run(
            ["blkid", "-s", "UUID", "-o", "value", device],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        return fs_uuid or None
    except (OSError, subprocess.SubprocessError):
        return None


def scan_volume(mount_dir: Path) -> dict[str, list[dict]]:
    """{carpeta_relativa: [{relpath, size, mtime}, ...]} para cada carpeta con
    al menos una imagen dentro de mount_dir."""
    folders: dict[str, list[dict]] = {}
    for root, _dirs, files in os.walk(mount_dir):
        images = [f for f in files if Path(f).suffix.lower() in IMAGE_EXTS]
        if not images:
            continue
        folder_relpath = os.path.relpath(root, mount_dir)
        entries = []
        for name in images:
            path = Path(root) / name
            try:
                stat = path.stat()
            except OSError:
                continue
            entries.append(
                {
                    "relpath": os.path.relpath(path, mount_dir),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                }
            )
        if entries:
            folders[folder_relpath] = entries
    return folders


def build_heartbeat_payload(mount_dirs: list[Path]) -> tuple[dict, dict[str, Path]]:
    volumes = []
    mount_dir_by_uuid: dict[str, Path] = {}
    for mount_dir in mount_dirs:
        fs_uuid = resolve_fs_uuid(mount_dir)
        if fs_uuid is None:
            print(f"usb-import: no pude resolver el UUID de {mount_dir}, la salteo", file=sys.stderr)
            continue
        folders = scan_volume(mount_dir)
        if not folders:
            continue
        mount_dir_by_uuid[fs_uuid] = mount_dir
        volumes.append(
            {
                "fs_uuid": fs_uuid,
                "label": mount_dir.name,
                "folders": [{"relpath": relpath, "files": files} for relpath, files in folders.items()],
            }
        )
    return {"volumes": volumes}, mount_dir_by_uuid


def run_cycle() -> None:
    mount_dirs = find_mount_dirs()
    payload, mount_dir_by_uuid = build_heartbeat_payload(mount_dirs)

    status, result = http_json("POST", "/admin/usb/heartbeat", payload)
    if status != 200:
        login()
        status, result = http_json("POST", "/admin/usb/heartbeat", payload)
    if result is None:
        return

    for entry in result.get("new_files", []):
        mount_dir = mount_dir_by_uuid.get(entry["fs_uuid"])
        if mount_dir is None:
            continue
        file_path = mount_dir / entry["relpath"]
        try:
            stat = file_path.stat()
        except OSError:
            continue
        fields = {
            "album_id": str(entry["album_id"]),
            "source_relpath": entry["relpath"],
            "source_size": str(stat.st_size),
            "source_mtime": str(stat.st_mtime),
        }
        http_upload("/admin/usb/photos", fields, file_path)

    for entry in result.get("pending_copies", []):
        mount_dir = mount_dir_by_uuid.get(entry["fs_uuid"])
        if mount_dir is None:
            continue
        file_path = mount_dir / entry["source_relpath"]
        if not file_path.exists():
            continue
        http_upload(f"/admin/usb/photos/{entry['photo_id']}/copy-complete", {}, file_path)


def wait_for_backend() -> None:
    for _ in range(60):
        try:
            with opener.open(f"{base_url()}/display", timeout=3):
                return
        except (urllib.error.URLError, http.client.HTTPException, OSError):
            time.sleep(1)


def main() -> None:
    wait_for_backend()
    login()
    while True:
        run_cycle()
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
