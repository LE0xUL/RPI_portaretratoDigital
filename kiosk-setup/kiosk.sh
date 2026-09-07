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
  sleep 5
done
