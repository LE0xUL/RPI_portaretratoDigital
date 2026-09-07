#!/usr/bin/env bash
set -euo pipefail

systemctl --user disable --now photoframe-screen.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/photoframe-screen.service"
rm -f "$HOME/.config/autostart/photoframe-kiosk.desktop"
systemctl --user daemon-reload

echo "Kiosk y scheduler de pantalla desinstalados. El contenedor Docker no se toca."
