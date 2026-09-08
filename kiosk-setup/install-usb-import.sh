#!/usr/bin/env bash
# Instala el auto-import de fotos desde USB. Es OPCIONAL y separado de
# install.sh a propósito: una vez activo, CUALQUIER USB que conectes a la Pi
# va a tener sus fotos subidas automáticamente a la biblioteca. Si eso no es
# lo que querés (por ejemplo, USBs que uses para otras cosas), no lo instales.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$EUID" -eq 0 ]; then
  echo "No corras este script con sudo/root. Se instala para el usuario actual." >&2
  exit 1
fi

chmod +x "$SCRIPT_DIR/usb-import.sh"

SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_USER_DIR"
sed "s|__USB_IMPORT_SH_PATH__|$SCRIPT_DIR/usb-import.sh|" \
  "$SCRIPT_DIR/photoframe-usb-import.service.template" > "$SYSTEMD_USER_DIR/photoframe-usb-import.service"

systemctl --user daemon-reload
systemctl --user enable --now photoframe-usb-import.service

cat <<EOF

Listo. photoframe-usb-import.service está corriendo: cada 15s revisa /media y
/mnt en busca de unidades USB y sube las fotos nuevas (jpg/jpeg/png/bmp/tiff/webp)
que encuentre, sin borrar nada del USB.

Para ver qué está haciendo:
  journalctl --user -u photoframe-usb-import.service -f

Para desactivarlo más adelante:
  ./uninstall-usb-import.sh
EOF
