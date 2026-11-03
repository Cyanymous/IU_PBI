"""Konfiguration Apache Superset für das Biofood-DWH. Alle Geheimnisse kommen aus der .env."""

import os

from sqlalchemy.engine import URL

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]

# Metadaten von Superset (Nutzer, Charts, Dashboards) in eigener Datenbank "superset"
SQLALCHEMY_DATABASE_URI = URL.create(
    "postgresql+psycopg2",
    username=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    host="db",
    port=5432,
    database="superset",
).render_as_string(hide_password=False)

# Deutsche Oberfläche, Englisch als Alternative
BABEL_DEFAULT_LOCALE = "de"
LANGUAGES = {
    "de": {"flag": "de", "name": "Deutsch"},
    "en": {"flag": "us", "name": "English"},
}

# Abfragen über 21 Mio. Fakten ohne Indizes brauchen Zeit: Timeouts erhöhen (Standard 30/60 s)
SQLLAB_TIMEOUT = 300
SUPERSET_WEBSERVER_TIMEOUT = 300

# Ergebnis-Cache: Daten ändern sich nur durch den ETL-Lauf, daher Chart-Ergebnisse 24 h vorhalten
DATA_CACHE_CONFIG = {
    "CACHE_TYPE": "FileSystemCache",
    "CACHE_DIR": "/app/superset_home/cache",
    "CACHE_DEFAULT_TIMEOUT": 60 * 60 * 24,
}

# Deutsches Zahlen- und Datumsformat in Charts (1.234,56 €, deutsche Monatsnamen)
D3_FORMAT = {
    "decimal": ",",
    "thousands": ".",
    "grouping": [3],
    "currency": ["", " €"],
}
D3_TIME_FORMAT = {
    "dateTime": "%A, der %e. %B %Y, %X",
    "date": "%d.%m.%Y",
    "time": "%H:%M:%S",
    "periods": ["AM", "PM"],
    "days": ["Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"],
    "shortDays": ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"],
    "months": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September",
               "Oktober", "November", "Dezember"],
    "shortMonths": ["Jan", "Feb", "Mrz", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"],
}
