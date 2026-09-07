# Portarretrato Digital

Convertí una Raspberry Pi conectada a una pantalla en un portarretrato digital: subís y organizás
fotos desde un panel web, y la pantalla muestra un slideshow con overlays de reloj/fecha/clima,
transiciones, y horario de encendido/apagado automático.

- **Backend**: FastAPI + SQLite.
- **Panel admin**: server-rendered con Jinja2 + HTMX + Alpine (sin build step).
- **Kiosk**: Docker corre solo el backend; el navegador en modo kiosk se lanza en el host (ver `kiosk-setup/`).

## Quickstart (backend, vía Docker)

```bash
git clone <este-repo>
cd RPI_portaretratoDigital
cp .env.example .env
# Editá .env: INVITE_CODE y SECRET_KEY (generá algo random, ver el propio .env.example)
docker compose up -d --build
```

Desde otra máquina en la misma red:

```
http://<ip-de-la-raspberry>:8080/login
```

Ingresá el `INVITE_CODE`, subí fotos, creá un álbum y marcalo como activo (o dejá todos inactivos
para mostrar la biblioteca completa). La sesión queda guardada ~1 año, así que no te lo va a volver
a pedir seguido.

## Modo kiosk (solo en la Raspberry Pi)

Una vez que el contenedor está corriendo y accesible en `http://localhost:8080`, en la propia
Raspberry Pi (con sesión gráfica de Raspberry Pi OS Desktop):

```bash
cd kiosk-setup
./install.sh
```

Esto instala Chromium (si falta), configura el autostart en modo kiosk apuntando a `/display`, y
habilita un servicio que apaga/prende la pantalla según el horario que configures en
`/admin/settings`. Detalles y troubleshooting en [`kiosk-setup/README.md`](kiosk-setup/README.md).

## Requisitos

- Raspberry Pi 4 o 5, Raspberry Pi OS **Desktop** de 64 bits (con sesión gráfica).
- Docker y Docker Compose instalados en la Pi.
- Acceso solo por red local (LAN) — no hay HTTPS ni exposición a Internet en esta versión.

## Estructura del repo

```
app/              backend FastAPI (modelos, rutas, lógica de imágenes/clima/horario)
templates/        vistas Jinja2 (panel admin + vista display)
static/           CSS/JS (htmx y alpine vendorizados, sin build step)
data/             volumen persistente: fotos y base de datos SQLite (gitignored)
kiosk-setup/       scripts para el host: autostart de Chromium + apagado programado de pantalla
tests/            smoke tests con pytest + TestClient
```

## Desarrollo local (sin Docker)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8080
pytest
```

## Backup y actualización

```bash
# Backup: todo lo importante vive en data/
tar czf backup-$(date +%F).tgz data/

# Actualizar a la última versión
git pull
docker compose up -d --build
```

## Troubleshooting

- **Puerto 8080 ocupado**: cambiá `PORT` en `.env` y volvé a levantar el contenedor.
- **Fotos HEIC de iPhone no se suben**: Pillow no soporta HEIC out of the box; convertilas a JPG antes
  de subirlas, o agregá `pillow-heif` a `requirements.txt` y `image_utils.py` si querés soporte nativo.
- **El kiosk no arranca en la Pi**: ver [`kiosk-setup/README.md`](kiosk-setup/README.md).
