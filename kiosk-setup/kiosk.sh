#!/usr/bin/env bash
# Lanza Chromium en modo kiosk apuntando al servicio Docker local.
# Pensado para correr como autostart de la sesión gráfica (ver photoframe-kiosk.desktop).
set -u

PORT="${PHOTOFRAME_PORT:-8080}"
URL="http://localhost:${PORT}/display"

# Espera a que el backend responda (útil tras un reboot, mientras Docker arranca)
for i in $(seq 1 60); do
  if curl -sf "$URL" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Desactiva el blanking/salvapantallas del compositor: el apagado de pantalla lo
# controla exclusivamente screen-schedule.sh (vcgencmd), para evitar que ambos
# mecanismos entren en conflicto.
if command -v xset >/dev/null 2>&1; then
  xset s off -dpms 2>/dev/null || true
fi

CHROMIUM_BIN="$(command -v chromium || command -v chromium-browser)"

# Si power-listener.sh pidió "ocultar N segundos" (menú de apagado del display),
# deja esta marca con el timestamp hasta el cual no hay que relanzar Chromium.
SUPPRESS_FILE="/tmp/photoframe-kiosk-suppress-until"

while true; do
  "$CHROMIUM_BIN" \
    --kiosk "--app=${URL}" \
    --noerrdialogs \
    --disable-infobars \
    --no-first-run \
    --disable-session-crashed-bubble \
    --disable-features=TranslateUI \
    --check-for-update-interval=31536000 \
    --autoplay-policy=no-user-gesture-required \
    --overscroll-history-navigation=0

  if [ -f "$SUPPRESS_FILE" ]; then
    until_ts="$(cat "$SUPPRESS_FILE" 2>/dev/null || echo 0)"
    remaining=$(( until_ts - $(date +%s) ))
    rm -f "$SUPPRESS_FILE"
    if [ "$remaining" -gt 0 ]; then
      sleep "$remaining"
    fi
  else
    sleep 5
  fi
done
