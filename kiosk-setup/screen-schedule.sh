#!/usr/bin/env bash
# Consulta periódicamente al backend si la pantalla debería estar encendida
# (según el horario configurado en /admin/settings), apaga/prende la señal
# HDMI real, y de paso baja/restaura la frecuencia de CPU (modo de bajo
# consumo) en el mismo cambio de estado. Corre como servicio systemd --user
# (ver photoframe-screen.service).
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PHOTOFRAME_PORT:-8080}"
STATUS_URL="http://localhost:${PORT}/api/display/screen-status"
POLL_SECONDS=60

last_status=""

set_power() {
  local on="$1"  # "true" | "false"
  if command -v vcgencmd >/dev/null 2>&1; then
    if [ "$on" = "true" ]; then
      vcgencmd display_power 1 >/dev/null 2>&1
    else
      vcgencmd display_power 0 >/dev/null 2>&1
    fi
  elif command -v xset >/dev/null 2>&1; then
    # Fallback para X11 genérico (no funciona en el compositor Wayland default de RPi OS)
    if [ "$on" = "true" ]; then
      xset dpms force on
    else
      xset dpms force off
    fi
  fi

  if [ "$on" = "true" ]; then
    sudo "$SCRIPT_DIR/cpu-throttle-apply.sh" normal 2>/dev/null || true
  else
    sudo "$SCRIPT_DIR/cpu-throttle-apply.sh" low 2>/dev/null || true
  fi
}

while true; do
  status=$(curl -sf "$STATUS_URL" | grep -o '"screen_on":[a-z]*' | cut -d: -f2)
  if [ -n "$status" ] && [ "$status" != "$last_status" ]; then
    set_power "$status"
    last_status="$status"
  fi
  sleep "$POLL_SECONDS"
done
