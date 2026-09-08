#!/usr/bin/env bash
# Escanea unidades USB montadas (auto-montaje del escritorio, típicamente en
# /media/$USER/<VOLUMEN>) y sube las fotos nuevas al backend, reusando el
# mismo endpoint que usa el panel admin. Corre en el host, no en Docker: el
# contenedor no ve unidades que el escritorio monta dinámicamente después de
# que arrancó, salvo configuración especial de propagación de mounts que es
# frágil entre distintos setups — este approach evita ese problema por completo.
#
# No borra nada de la USB: solo copia (sube) lo que todavía no subió.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$REPO_ROOT/.env"

STATE_DIR="$HOME/.local/state/photoframe"
mkdir -p "$STATE_DIR"
IMPORTED_LIST="$STATE_DIR/usb-imported.tsv"   # checksum<TAB>ruta ya importada
COOKIE_JAR="$STATE_DIR/session-cookie.txt"
touch "$IMPORTED_LIST"

POLL_SECONDS=15

read_env_var() {
  # read_env_var NOMBRE default
  local name="$1" default="$2"
  if [ -f "$ENV_FILE" ]; then
    local value
    value="$(grep -E "^${name}=" "$ENV_FILE" | tail -1 | cut -d= -f2-)"
    [ -n "$value" ] && { echo "$value"; return; }
  fi
  echo "$default"
}

base_url() {
  echo "http://localhost:$(read_env_var PORT 8080)"
}

login() {
  local invite_code status
  invite_code="$(read_env_var INVITE_CODE "")"
  status="$(curl -s -o /dev/null -w '%{http_code}' -c "$COOKIE_JAR" \
    --data-urlencode "code=${invite_code}" "$(base_url)/login")"
  [ "$status" = "303" ]
}

upload_file() {
  # OJO: no usar `curl -f` acá — si la sesión no es válida, /admin/photos
  # responde 303 (redirect a /login), y `curl -f` solo falla con 4xx/5xx,
  # así que un 303 se leería como "éxito" sin haber subido nada.
  local file="$1" display_name="$2" status
  status="$(curl -s -o /dev/null -w '%{http_code}' -b "$COOKIE_JAR" \
    -F "files=@${file};filename=${display_name}" "$(base_url)/admin/photos")"
  [ "$status" = "200" ]
}

find_media_dirs() {
  # /media/<usuario>/<VOLUMEN> es donde Raspberry Pi OS Desktop automonta USB.
  # /mnt/<algo> como respaldo por si el usuario montó algo manualmente ahí.
  {
    find /media -mindepth 2 -maxdepth 2 -type d -print0 2>/dev/null
    find /mnt -mindepth 1 -maxdepth 1 -type d -print0 2>/dev/null
  }
}

# Espera a que el backend responda (por si arranca antes que Docker tras un reboot)
for _ in $(seq 1 60); do
  curl -sf "$(base_url)/display" >/dev/null 2>&1 && break
  sleep 1
done
login || true

while true; do
  while IFS= read -r -d '' dir; do
    volume_label="$(basename "$dir")"
    while IFS= read -r -d '' file; do
      checksum="$(sha256sum "$file" | cut -d' ' -f1)"
      if grep -qF "$checksum" "$IMPORTED_LIST" 2>/dev/null; then
        continue
      fi

      display_name="USB-${volume_label}__$(basename "$file")"
      if ! upload_file "$file" "$display_name"; then
        login
        upload_file "$file" "$display_name" || continue
      fi
      printf '%s\t%s\n' "$checksum" "$file" >> "$IMPORTED_LIST"
    done < <(find "$dir" -regextype posix-extended -iregex '.*\.(jpe?g|png|bmp|tiff?|webp)' -type f -print0 2>/dev/null)
  done < <(find_media_dirs)

  sleep "$POLL_SECONDS"
done
