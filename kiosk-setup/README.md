# kiosk-setup

Estos scripts corren **fuera de Docker, directamente en la Raspberry Pi**, y hacen dos cosas:

1. Lanzan Chromium en modo kiosk apuntando a `http://localhost:PORT/display` cada vez que iniciás sesión gráfica (`kiosk.sh` + `photoframe-kiosk.desktop`).
2. Prenden/apagan la señal HDMI real según el horario configurado en el panel admin (`screen-schedule.sh`, corriendo como servicio `systemd --user`).

No tocan el contenedor Docker en absoluto — solo consumen su API vía HTTP local.

## Requisitos

- Raspberry Pi OS **Desktop** (con sesión gráfica X11 o Wayland/Wayfire), auto-login habilitado.
- El contenedor ya levantado: `docker compose up -d --build` desde la raíz del repo.
- Chromium (el script de instalación lo instala si falta).

## Instalación

```bash
cd kiosk-setup
./install.sh
```

Si tu servicio Docker corre en un puerto distinto de 8080, exportá `PHOTOFRAME_PORT` antes de correr `install.sh`:

```bash
PHOTOFRAME_PORT=9000 ./install.sh
```

Después, cerrá sesión y volvé a entrar (o reiniciá la Pi) para que el autostart tome efecto.

## Por qué dos mecanismos de apagado de pantalla

- La vista `/display` ya pone la pantalla en negro por su cuenta (JS + polling), sin depender de nada de esto — funciona incluso si nunca corrés `install.sh` (útil para probar en una laptop).
- `screen-schedule.sh` va un paso más allá y apaga la señal HDMI de verdad con `vcgencmd display_power` (ahorra energía real y reduce desgaste de pantalla), con algo más de latencia (hasta 60s) respecto al negro en pantalla.

## Desinstalar

```bash
cd kiosk-setup
./uninstall.sh
```

## Troubleshooting

- **Chromium no arranca al bootear**: revisá que `~/.config/autostart/photoframe-kiosk.desktop` exista y que el auto-login gráfico esté activo (`sudo raspi-config` → System Options → Boot / Auto Login → Desktop Autologin).
- **La pantalla no se apaga/prende con el horario**: `journalctl --user -u photoframe-screen.service -f`. Confirmá que `vcgencmd` existe (`which vcgencmd`) — es específico de Raspberry Pi OS.
- **Orientación portrait rara**: el fallback CSS (rotación vía `transform`) funciona, pero para mejores resultados rotá la pantalla a nivel sistema (`xrandr` en X11, o la config del compositor en Wayfire) y dejá `display_orientation=landscape` en settings.
