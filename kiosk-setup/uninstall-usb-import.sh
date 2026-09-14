#!/usr/bin/env bash
set -euo pipefail

systemctl --user disable --now photoframe-usb-import.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/photoframe-usb-import.service"
systemctl --user daemon-reload

echo "Detección automática de USB desinstalada."
echo "Los álbumes/fotos que ya se hayan creado a partir de unidades USB quedan"
echo "en el dashboard tal cual estaban (podés borrarlos a mano en Álbumes)."
