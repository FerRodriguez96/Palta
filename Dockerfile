FROM debian:12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

# Dependencias del sistema: Python y librerías necesarias para compilar
# algunas dependencias de Google (grpc/cryptography)
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        build-essential \
        libffi-dev \
        libssl-dev \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Entorno virtual para no pelear con el Python del sistema en Debian
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/instance /app/logs /app/downloads

# Usuario sin privilegios
RUN useradd --create-home --shell /bin/bash palta \
    && chown -R palta:palta /app
USER palta

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD curl -f http://localhost:5000/estado || exit 1

CMD ["python3", "main.py"]
