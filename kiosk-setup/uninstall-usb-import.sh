#!/usr/bin/env bash
set -euo pipefail

systemctl --user disable --now photoframe-usb-import.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/photoframe-usb-import.service"
systemctl --user daemon-reload

echo "Auto-import de USB desinstalado."
echo "El historial de qué ya se importó sigue en ~/.local/state/photoframe/usb-imported.tsv"
echo "(borralo a mano si querés que la próxima vez se re-suban archivos ya importados)."
