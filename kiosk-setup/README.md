# kiosk-setup

Estos scripts corren **fuera de Docker, directamente en la Raspberry Pi**, y hacen tres cosas:

1. Lanzan Chromium en modo kiosk apuntando a `http://localhost:PORT/display` cada vez que iniciás sesión gráfica (`kiosk.sh` + `photoframe-kiosk.desktop`).
2. Prenden/apagan la señal HDMI real según el horario configurado en el panel admin (`screen-schedule.sh`, corriendo como servicio `systemd --user`).
3. Escuchan el menú de apagado del propio `/display` — 3 toques en la esquina superior izquierda de la pantalla abren un menú táctil con **Apagar / Reiniciar / Ocultar 2 min** (`power-listener.sh`, también como servicio `systemd --user`).

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

`install.sh` también instala una regla en `/etc/sudoers.d/photoframe-power` que permite a tu
usuario correr **solo** `/sbin/shutdown` y `/sbin/reboot` sin contraseña (necesario para que el
menú de apagado funcione) — no es un `sudo` general, el archivo limita explícitamente esos dos
comandos.

## Por qué dos mecanismos de apagado de pantalla

- La vista `/display` ya pone la pantalla en negro por su cuenta (JS + polling), sin depender de nada de esto — funciona incluso si nunca corrés `install.sh` (útil para probar en una laptop).
- `screen-schedule.sh` va un paso más allá y apaga la señal HDMI de verdad con `vcgencmd display_power` (ahorra energía real y reduce desgaste de pantalla), con algo más de latencia (hasta 60s) respecto al negro en pantalla.

## Menú de apagado táctil (3 toques)

En `/display`, tocar 3 veces (en menos de 1.5s) la esquina superior izquierda de la pantalla abre
un menú con:

- **Apagar Raspberry Pi**: corre `sudo shutdown -h now` en el host. Esperá el mensaje en pantalla
  antes de desconectar la alimentación.
- **Reiniciar Raspberry Pi**: `sudo reboot`.
- **Ocultar 2 min**: cierra Chromium por 2 minutos (útil para usar la pantalla táctil para otra
  cosa un rato) y se vuelve a abrir solo — no hace falta teclado para recuperarlo.
- **Cancelar**: cierra el menú (también se cierra solo a los 10s sin uso).

El navegador nunca ejecuta estas acciones directamente: solo le avisa al backend ("quiero
apagar"), vía `POST /api/display/power-action`. `power-listener.sh` (corriendo en el host, no en
Docker) hace polling cada 2s de `GET /api/display/power-status` y ejecuta la acción real. Este
endpoint no requiere el código de invitación (mismo modelo de confianza que el resto de
`/display`: solo LAN, acceso físico a la pantalla ya implica poder desenchufar la Pi de todos
modos).

## Desinstalar

```bash
cd kiosk-setup
./uninstall.sh
```

## Troubleshooting

- **Chromium no arranca al bootear**: revisá que `~/.config/autostart/photoframe-kiosk.desktop` exista y que el auto-login gráfico esté activo (`sudo raspi-config` → System Options → Boot / Auto Login → Desktop Autologin).
- **La pantalla no se apaga/prende con el horario**: `journalctl --user -u photoframe-screen.service -f`. Confirmá que `vcgencmd` existe (`which vcgencmd`) — es específico de Raspberry Pi OS.
- **El menú de apagado no hace nada**: `journalctl --user -u photoframe-power.service -f` mientras tocás el menú. Si dice `sudo: a password is required`, la regla de `/etc/sudoers.d/photoframe-power` no quedó bien instalada — corré `sudo visudo -c` para validarla, o volvé a correr `install.sh`.
- **Orientación portrait rara**: el fallback CSS (rotación vía `transform`) funciona, pero para mejores resultados rotá la pantalla a nivel sistema (`xrandr` en X11, o la config del compositor en Wayfire) y dejá `display_orientation=landscape` en settings.
