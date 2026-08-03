#!/bin/bash
# Backup de instance/ (base de datos + credenciales de Drive/YouTube) para PALTA.
# Pensado para correr desde cron en el HOST (no dentro del contenedor), ya que
# instance/ es un volumen montado y existe igual en el filesystem del servidor.
#
# Uso manual: ./backup.sh
# Uso en cron (backup diario a las 3am), agregar con `crontab -e`:
#   0 3 * * * /ruta/completa/a/palta-web/backup.sh >> /ruta/completa/a/palta-web/backup.log 2>&1

set -e

PROYECTO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FECHA=$(date +%Y-%m-%d_%H-%M)
DESTINO="$PROYECTO_DIR/backups/$FECHA"
DIAS_A_CONSERVAR=14

mkdir -p "$DESTINO"
cp -r "$PROYECTO_DIR/instance" "$DESTINO/"

echo "[$(date)] Backup guardado en $DESTINO"

# Rotacion: se conservan solo los ultimos N backups (por cantidad, no por
# fecha, para no depender de que el cron corra todos los dias sin falta).
cd "$PROYECTO_DIR/backups"
ls -1t | tail -n +$((DIAS_A_CONSERVAR + 1)) | while read -r viejo; do
    rm -rf "$viejo"
    echo "[$(date)] Backup antiguo eliminado: $viejo"
done
