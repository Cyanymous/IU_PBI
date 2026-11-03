"""L – Load: schreibt Dimensionen und Fakten per Upsert ins DWH.

Wiederholbarkeit: Alle Tabellen werden mit INSERT ... ON CONFLICT DO UPDATE beladen.
Vorhandene Schlüssel werden bei jedem Lauf vollständig überschrieben, neue angehängt.
"""

import io
import os

from sqlalchemy import URL, create_engine, text


def engine():
    url = URL.create(
        "postgresql+psycopg2",
        username=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        database=os.environ["DB_NAME"],
    )
    return create_engine(url)


# ---------------------------------------------------------------- Dimensionen

def dim_filiale(conn, df):
    conn.execute(text("""
        INSERT INTO dim_filiale (filiale_id, filiale, bundesland, ort)
        VALUES (:filiale_id, :filiale, :bundesland, :ort)
        ON CONFLICT (filiale_id) DO UPDATE
           SET filiale = EXCLUDED.filiale, bundesland = EXCLUDED.bundesland, ort = EXCLUDED.ort
    """), df.to_dict("records"))


def dim_sku(conn, df):
    conn.execute(text("""
        INSERT INTO dim_sku (artikelnummer, artikelname, stueckpreis, kategorie_nr, kategorie_name)
        VALUES (:artikelnummer, :artikelname, :stueckpreis, :kategorie_nr, :kategorie_name)
        ON CONFLICT (artikelnummer) DO UPDATE
           SET artikelname = EXCLUDED.artikelname, stueckpreis = EXCLUDED.stueckpreis,
               kategorie_nr = EXCLUDED.kategorie_nr, kategorie_name = EXCLUDED.kategorie_name
    """), df.to_dict("records"))


def dim_datum(conn, zeilen):
    spalten = list(zeilen[0].keys())
    updates = ", ".join(f"{s} = EXCLUDED.{s}" for s in spalten if s != "datum")
    conn.execute(text(f"""
        INSERT INTO dim_datum ({", ".join(spalten)})
        VALUES ({", ".join(":" + s for s in spalten)})
        ON CONFLICT (datum) DO UPDATE SET {updates}
    """), zeilen)


# ---------------------------------------------------------------- Staging

def erstelle_staging(conn):
    """Temporäre Tabelle, existiert nur in dieser Transaktion."""
    conn.execute(text("""
        CREATE TEMP TABLE stg_verkauf (
            filiale_id VARCHAR(5), kauf_nr INTEGER, artikelnummer INTEGER,
            datum_key INTEGER, anzahl INTEGER
        ) ON COMMIT DROP
    """))


def staging(conn, df):
    """Massenimport per COPY, um ein Vielfaches schneller als einzelne INSERTs."""
    puffer = io.StringIO()
    df[["filiale_id", "kauf_nr", "artikelnummer", "datum_key", "anzahl"]].to_csv(
        puffer, index=False, header=False)
    puffer.seek(0)
    cur = conn.connection.cursor()
    cur.copy_expert("COPY stg_verkauf (filiale_id, kauf_nr, artikelnummer, datum_key, anzahl) "
                    "FROM STDIN WITH (FORMAT csv)", puffer)
    cur.close()


def unbekannte_schluessel(conn):
    """Positionen, deren Filiale oder Artikel nicht in den Dimensionen steht."""
    return conn.execute(text("""
        SELECT s.filiale_id, s.artikelnummer, count(*) AS zeilen
          FROM stg_verkauf s
          LEFT JOIN dim_filiale f ON f.filiale_id = s.filiale_id
          LEFT JOIN dim_sku k     ON k.artikelnummer = s.artikelnummer
         WHERE f.filiale_key IS NULL OR k.artikelnummer_key IS NULL
         GROUP BY s.filiale_id, s.artikelnummer
         ORDER BY zeilen DESC
    """)).fetchall()


# ---------------------------------------------------------------- Fakten

def fakt_verkauf(conn):
    """Surrogate Keys per JOIN auf die Dimensionen, Upsert auf den Fakten-PK.

    Gibt (neue Zeilen, überschriebene Zeilen) zurück.
    """
    vorher = conn.execute(text("SELECT count(*) FROM fakt_verkauf")).scalar()
    geschrieben = conn.execute(text("""
        INSERT INTO fakt_verkauf (artikelnummer_key, filiale_key, datum_key, kauf_nr, anzahl)
        SELECT k.artikelnummer_key, f.filiale_key, s.datum_key, s.kauf_nr, s.anzahl
          FROM stg_verkauf s
          JOIN dim_filiale f ON f.filiale_id = s.filiale_id
          JOIN dim_sku k     ON k.artikelnummer = s.artikelnummer
        ON CONFLICT (filiale_key, kauf_nr, artikelnummer_key) DO UPDATE
           SET datum_key = EXCLUDED.datum_key, anzahl = EXCLUDED.anzahl
    """)).rowcount
    nachher = conn.execute(text("SELECT count(*) FROM fakt_verkauf")).scalar()
    neu = nachher - vorher
    return neu, geschrieben - neu
