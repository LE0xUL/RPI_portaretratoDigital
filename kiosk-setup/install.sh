#!/usr/bin/env bash
# Configura el autostart del modo kiosk y el scheduler de encendido/apagado
# de pantalla en esta Raspberry Pi. Correr con la sesión gráfica normal
# (NO con sudo), después de haber levantado el contenedor con `docker compose up -d`.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Si no se pasó PHOTOFRAME_PORT explícitamente, lo tomamos del PORT= del .env
# de la raíz del repo (el mismo que usa docker-compose.yml), para no tener que
# repetirlo a mano y evitar que kiosk/screen-schedule apunten a un puerto distinto
# del que realmente expone el contenedor.
if [ -z "${PHOTOFRAME_PORT:-}" ] && [ -f "$REPO_ROOT/.env" ]; then
  PHOTOFRAME_PORT="$(grep -E '^PORT=' "$REPO_ROOT/.env" | tail -1 | cut -d= -f2-)"
fi
PORT="${PHOTOFRAME_PORT:-8080}"
echo "Usando PHOTOFRAME_PORT=$PORT"

if [ "$EUID" -eq 0 ]; then
  echo "No corras este script con sudo/root. Se instala para el usuario actual." >&2
  exit 1
fi

if ! command -v chromium >/dev/null 2>&1 && ! command -v chromium-browser >/dev/null 2>&1; then
  echo "Chromium no está instalado. Instalando..."
  sudo apt-get update
  sudo apt-get install -y chromium-browser || sudo apt-get install -y chromium
fi

chmod +x "$SCRIPT_DIR/kiosk.sh" "$SCRIPT_DIR/screen-schedule.sh" "$SCRIPT_DIR/power-listener.sh" \
  "$SCRIPT_DIR/cpu-throttle-apply.sh"

# --- Regla de sudoers acotada, sin contraseña, para este usuario:
#   - /sbin/shutdown y /sbin/reboot: para el menú de apagado del /display (3 toques).
#   - cpu-throttle-apply.sh low|normal: para bajar/restaurar la frecuencia de CPU
#     fuera del horario activo (modo de bajo consumo, junto con la pantalla).
# No es un "sudo sin restricciones": el propio archivo limita los comandos
# exactos (con sus argumentos exactos) que se pueden correr.
SUDOERS_FILE="/etc/sudoers.d/photoframe-power"
SUDOERS_CONTENT="$USER ALL=(root) NOPASSWD: /sbin/shutdown, /sbin/reboot, $SCRIPT_DIR/cpu-throttle-apply.sh low, $SCRIPT_DIR/cpu-throttle-apply.sh normal"
if [ ! -f "$SUDOERS_FILE" ] || ! grep -qF "$SUDOERS_CONTENT" "$SUDOERS_FILE" 2>/dev/null; then
  echo "$SUDOERS_CONTENT" | sudo tee "$SUDOERS_FILE" >/dev/null
  sudo chmod 0440 "$SUDOERS_FILE"
  sudo visudo -c -f "$SUDOERS_FILE" >/dev/null || {
    echo "La regla de sudoers generada no es válida, revirtiendo." >&2
    sudo rm -f "$SUDOERS_FILE"
    exit 1
  }
  echo "Regla de sudoers instalada en $SUDOERS_FILE (shutdown/reboot/cpu-throttle, sin password)."
fi

# --- Autostart de Chromium en modo kiosk (XDG autostart, funciona en X11 y Wayfire/labwc) ---
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
sed \
  -e "s|__KIOSK_SH_PATH__|$SCRIPT_DIR/kiosk.sh|" \
  -e "s|__PHOTOFRAME_PORT__|$PORT|" \
  "$SCRIPT_DIR/photoframe-kiosk.desktop.template" > "$AUTOSTART_DIR/photoframe-kiosk.desktop"
echo "Autostart instalado en $AUTOSTART_DIR/photoframe-kiosk.desktop"

# --- Servicio systemd --user para el scheduler de encendido/apagado de pantalla ---
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_USER_DIR"
sed \
  -e "s|__SCREEN_SCHEDULE_SH_PATH__|$SCRIPT_DIR/screen-schedule.sh|" \
  -e "s|__PHOTOFRAME_PORT__|$PORT|" \
  "$SCRIPT_DIR/photoframe-screen.service.template" > "$SYSTEMD_USER_DIR/photoframe-screen.service"


# --- Servicio systemd --user para el listener del menú de apagado (3 toques en /display) ---
sed \
  -e "s|__POWER_LISTENER_SH_PATH__|$SCRIPT_DIR/power-listener.sh|" \
  -e "s|__PHOTOFRAME_PORT__|$PORT|" \
  "$SCRIPT_DIR/photoframe-power.service.template" > "$SYSTEMD_USER_DIR/photoframe-power.service"

systemctl --user daemon-reload
systemctl --user enable --now photoframe-screen.service
systemctl --user enable --now photoframe-power.service
echo "Servicios photoframe-screen.service y photoframe-power.service habilitados."

cat <<EOF

Listo. Para que el kiosk arranque, cerrá sesión y volvé a entrar (o reiniciá la Pi).

Si tenés habilitado el auto-login gráfico, esto alcanza. Si no, activalo desde
raspi-config (System Options > Boot / Auto Login > Desktop Autologin).

En el /display, 3 toques en la esquina superior izquierda abren el menú de
Apagar / Reiniciar / Ocultar 2 min.

Para ver logs:
  journalctl --user -u photoframe-screen.service -f
  journalctl --user -u photoframe-power.service -f
EOF
