#!/usr/bin/env bash
# Escucha el menú de apagado del /display (3 toques -> Apagar/Reiniciar/Ocultar) y
# ejecuta la acción del lado del host, ya que el contenedor Docker no puede tocar
# el sistema. Poll rápido (2s) porque acá el usuario está esperando una respuesta,
# a diferencia de screen-schedule.sh que solo necesita granularidad de minutos.
set -u

PORT="${PHOTOFRAME_PORT:-8080}"
STATUS_URL="http://localhost:${PORT}/api/display/power-status"
SUPPRESS_FILE="/tmp/photoframe-kiosk-suppress-until"
POLL_SECONDS=2

while true; do
  resp="$(curl -sf "$STATUS_URL" 2>/dev/null || true)"
  action="$(echo "$resp" | grep -o '"action":"[a-z]*"' | cut -d'"' -f4)"

  case "$action" in
    shutdown)
      sudo /sbin/shutdown -h now
      ;;
    reboot)
      sudo /sbin/reboot
      ;;
    hide)
      seconds="$(echo "$resp" | grep -o '"hide_seconds":[0-9]*' | cut -d: -f2)"
      seconds="${seconds:-120}"
      echo "$(( $(date +%s) + seconds ))" > "$SUPPRESS_FILE"
      pkill -f -- "--app=http://localhost:${PORT}/display" 2>/dev/null || true
      ;;
  esac

  sleep "$POLL_SECONDS"
done
