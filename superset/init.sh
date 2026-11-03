#!/usr/bin/env bash
# Einmalige Einrichtung von Superset (läuft im Service superset-init, wiederholbar)
set -euo pipefail

# 1. Metadaten-Schema in der DB "superset" anlegen bzw. aktualisieren
superset db upgrade

# 2. Admin anlegen (existiert er schon, meldet FAB das nur)
superset fab create-admin \
  --username admin \
  --firstname Admin \
  --lastname Biofood \
  --email admin@biofood.invalid \
  --password "$SUPERSET_ADMIN_PASSWORD"

# 3. Standardrollen und Berechtigungen initialisieren
superset init
