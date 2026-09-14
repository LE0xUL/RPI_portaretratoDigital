#!/usr/bin/env bash
# Instala la detección automática de USB. Es OPCIONAL y separado de
# install.sh a propósito: una vez activo, CUALQUIER USB que conectes a la Pi
# va a generar álbumes temporales con sus fotos. Si eso no es lo que querés
# (por ejemplo, USBs que uses para otras cosas), no lo instales.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$EUID" -eq 0 ]; then
  echo "No corras este script con sudo/root. Se instala para el usuario actual." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1 || ! command -v findmnt >/dev/null 2>&1 || ! command -v blkid >/dev/null 2>&1; then
  echo "Faltan dependencias: python3, findmnt y blkid (de util-linux) tienen que estar instalados." >&2
  exit 1
fi

chmod +x "$SCRIPT_DIR/usb-import.py"

SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_USER_DIR"
sed "s|__USB_IMPORT_PATH__|$SCRIPT_DIR/usb-import.py|" \
  "$SCRIPT_DIR/photoframe-usb-import.service.template" > "$SYSTEMD_USER_DIR/photoframe-usb-import.service"

systemctl --user daemon-reload
systemctl --user enable --now photoframe-usb-import.service

cat <<EOF

Listo. photoframe-usb-import.service está corriendo: cada 15s revisa /media y
/mnt en busca de unidades USB, y por cada carpeta de fotos que encuentre crea
(o reconecta) un álbum temporal activo en el dashboard. No copia nada del USB
por su cuenta -- desde "Álbumes" en el panel podés elegir qué copiar a la
biblioteca, álbum completo o foto por foto.

Para ver qué está haciendo:
  journalctl --user -u photoframe-usb-import.service -f

Para desactivarlo más adelante:
  ./uninstall-usb-import.sh
EOF
