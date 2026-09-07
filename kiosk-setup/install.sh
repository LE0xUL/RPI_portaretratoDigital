#!/usr/bin/env bash
# Configura el autostart del modo kiosk y el scheduler de encendido/apagado
# de pantalla en esta Raspberry Pi. Correr con la sesión gráfica normal
# (NO con sudo), después de haber levantado el contenedor con `docker compose up -d`.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PHOTOFRAME_PORT:-8080}"

if [ "$EUID" -eq 0 ]; then
  echo "No corras este script con sudo/root. Se instala para el usuario actual." >&2
  exit 1
fi

if ! command -v chromium >/dev/null 2>&1 && ! command -v chromium-browser >/dev/null 2>&1; then
  echo "Chromium no está instalado. Instalando..."
  sudo apt-get update
  sudo apt-get install -y chromium-browser || sudo apt-get install -y chromium
fi

chmod +x "$SCRIPT_DIR/kiosk.sh" "$SCRIPT_DIR/screen-schedule.sh"

# --- Autostart de Chromium en modo kiosk (XDG autostart, funciona en X11 y Wayfire/labwc) ---
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
sed "s|__KIOSK_SH_PATH__|$SCRIPT_DIR/kiosk.sh|" \
  "$SCRIPT_DIR/photoframe-kiosk.desktop.template" > "$AUTOSTART_DIR/photoframe-kiosk.desktop"
echo "Autostart instalado en $AUTOSTART_DIR/photoframe-kiosk.desktop"

# --- Servicio systemd --user para el scheduler de encendido/apagado de pantalla ---
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_USER_DIR"
sed \
  -e "s|__SCREEN_SCHEDULE_SH_PATH__|$SCRIPT_DIR/screen-schedule.sh|" \
  -e "s|__PHOTOFRAME_PORT__|$PORT|" \
  "$SCRIPT_DIR/photoframe-screen.service.template" > "$SYSTEMD_USER_DIR/photoframe-screen.service"

systemctl --user daemon-reload
systemctl --user enable --now photoframe-screen.service
echo "Servicio photoframe-screen.service habilitado."

cat <<EOF

Listo. Para que el kiosk arranque, cerrá sesión y volvé a entrar (o reiniciá la Pi).

Si tenés habilitado el auto-login gráfico, esto alcanza. Si no, activalo desde
raspi-config (System Options > Boot / Auto Login > Desktop Autologin).

Para ver logs del scheduler de pantalla:
  journalctl --user -u photoframe-screen.service -f
EOF
