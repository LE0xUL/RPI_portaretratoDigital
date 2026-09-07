FROM python:3.12-slim-bookworm

WORKDIR /app

# Si en tu Raspberry Pi corrés un OS de 32-bit (armv7) y no hay wheel
# prebuilt de Pillow para tu plataforma, descomentá estas líneas:
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     gcc libjpeg-dev zlib1g-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app
COPY templates/ ./templates
COPY static/ ./static

RUN useradd -m appuser && mkdir -p /app/data && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
