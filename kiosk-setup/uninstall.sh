#!/usr/bin/env bash
set -euo pipefail

systemctl --user disable --now photoframe-screen.service 2>/dev/null || true
systemctl --user disable --now photoframe-power.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/photoframe-screen.service"
rm -f "$HOME/.config/systemd/user/photoframe-power.service"
rm -f "$HOME/.config/autostart/photoframe-kiosk.desktop"
sudo rm -f /etc/sudoers.d/photoframe-power
systemctl --user daemon-reload

echo "Kiosk, scheduler de pantalla y menú de apagado desinstalados. El contenedor Docker no se toca."
