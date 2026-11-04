"""ETL: lädt einen Database Dump des operativen Systems ins Biofood-DWH.

Aufruf:  python main.py data/dumps/biofood_oltp_2024-12-31.sql.gz

E  Der Dump wird per psql in das Staging-Schema "quelle" wiederhergestellt.
T  Die Umformung steckt in den SELECTs: Kategorie wird in dim_sku aufgelöst, datum_key aus dem
   Kaufdatum abgeleitet, der Kalender erzeugt und die Surrogate Keys per JOIN nachgeschlagen.
L  Upserts: erst Dimensionen, dann Fakten. Vorhandene Schlüssel werden überschrieben, neue
   angehängt. Alles läuft in einer Transaktion, bei einem Fehler wird komplett zurückgerollt.

Die Zugangsdaten kommen aus den Umgebungsvariablen PGHOST, PGUSER, PGPASSWORD und PGDATABASE,
die psql und psycopg2 automatisch auswerten.
"""

import argparse
import gzip
import logging
import shutil
import subprocess
import time

import psycopg2

log = logging.getLogger("etl")

DIM_FILIALE = """
    INSERT INTO dim_filiale (filiale_id, bundesland, ort)
    SELECT filial_id, bundesland, ort
      FROM quelle.filiale
    ON CONFLICT (filiale_id) DO UPDATE
       SET bundesland = EXCLUDED.bundesland, ort = EXCLUDED.ort
"""

DIM_SKU = """
    INSERT INTO dim_sku (artikelnummer, artikelname, stueckpreis, kategorie_nr, kategorie_name)
    SELECT a.artikel_nr, a.artikel_name, a.stueckpreis, k.kategorie_nr, k.kategorie_name
      FROM quelle.artikel a
      JOIN quelle.kategorie k USING (kategorie_nr)
    ON CONFLICT (artikelnummer) DO UPDATE
       SET artikelname = EXCLUDED.artikelname, stueckpreis = EXCLUDED.stueckpreis,
           kategorie_nr = EXCLUDED.kategorie_nr, kategorie_name = EXCLUDED.kategorie_name
"""

# Kalender: alle Tage der vollständigen Jahre, in denen Einkäufe liegen
DIM_DATUM = """
    INSERT INTO dim_datum (datum_key, datum, datum_text, jahr, quartal, jahr_quartal, monat_nr,
                           monat_name, jahr_monat, kw, tag_im_monat, tag_im_jahr,
                           wochentag_nr, wochentag_name)
    SELECT to_char(t, 'YYYYMMDD')::int, t::date, to_char(t, 'DD.MM.YYYY'),
           extract(year FROM t), extract(quarter FROM t), to_char(t, 'YYYY-"Q"Q'),
           extract(month FROM t),
           (ARRAY['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August',
                  'September', 'Oktober', 'November', 'Dezember'])[extract(month FROM t)],
           to_char(t, 'YYYY-MM'), extract(week FROM t), extract(day FROM t), extract(doy FROM t),
           extract(isodow FROM t),
           (ARRAY['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag',
                  'Sonntag'])[extract(isodow FROM t)]
      FROM (SELECT min(kaufdatum) AS von, max(kaufdatum) AS bis FROM quelle.einkauf) z,
           generate_series(date_trunc('year', z.von),
                           date_trunc('year', z.bis) + interval '1 year - 1 day',
                           interval '1 day') AS t
    ON CONFLICT (datum_key) DO UPDATE
       SET datum = EXCLUDED.datum, datum_text = EXCLUDED.datum_text, jahr = EXCLUDED.jahr,
           quartal = EXCLUDED.quartal, jahr_quartal = EXCLUDED.jahr_quartal,
           monat_nr = EXCLUDED.monat_nr, monat_name = EXCLUDED.monat_name,
           jahr_monat = EXCLUDED.jahr_monat, kw = EXCLUDED.kw,
           tag_im_monat = EXCLUDED.tag_im_monat, tag_im_jahr = EXCLUDED.tag_im_jahr,
           wochentag_nr = EXCLUDED.wochentag_nr, wochentag_name = EXCLUDED.wochentag_name
"""

FAKT_VERKAUF = """
    INSERT INTO fakt_verkauf (artikelnummer_key, filiale_key, datum_key, kauf_nr, anzahl)
    SELECT s.artikelnummer_key, f.filiale_key, to_char(e.kaufdatum, 'YYYYMMDD')::int,
           e.kauf_nr, p.anzahl
      FROM quelle.einkauf_artikel p
      JOIN quelle.einkauf e USING (kauf_nr)
      JOIN dim_sku s        ON s.artikelnummer = p.artikel_nr
      JOIN dim_filiale f    ON f.filiale_id = e.filial_id
    ON CONFLICT (kauf_nr, artikelnummer_key) DO UPDATE
       SET filiale_key = EXCLUDED.filiale_key, datum_key = EXCLUDED.datum_key,
           anzahl = EXCLUDED.anzahl
"""


def extract(dump):
    """Stellt den Dump im Schema quelle wieder her, ein alter Rest wird vorher entfernt."""
    psql = subprocess.Popen(["psql", "-q", "-v", "ON_ERROR_STOP=1", "--single-transaction"],
                            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL)
    psql.stdin.write(b"DROP SCHEMA IF EXISTS quelle CASCADE;\n")
    with gzip.open(dump) as f:
        shutil.copyfileobj(f, psql.stdin)
    psql.stdin.close()
    if psql.wait() != 0:
        raise RuntimeError("Wiederherstellung des Dumps fehlgeschlagen")


def transform_load():
    """Überträgt die Daten aus quelle ins Star-Schema und entfernt danach das Staging-Schema."""
    with psycopg2.connect("") as conn, conn.cursor() as cur:
        for name, sql in [("dim_filiale", DIM_FILIALE), ("dim_sku", DIM_SKU), ("dim_datum", DIM_DATUM)]:
            cur.execute(sql)
            log.info("%s: %d Zeilen geschrieben", name, cur.rowcount)

        cur.execute("SELECT count(*) FROM fakt_verkauf")
        vorher = cur.fetchone()[0]
        cur.execute(FAKT_VERKAUF)
        geschrieben = cur.rowcount
        cur.execute("SELECT count(*) FROM fakt_verkauf")
        neu = cur.fetchone()[0] - vorher
        log.info("fakt_verkauf: %d neu, %d überschrieben", neu, geschrieben - neu)

        cur.execute("DROP SCHEMA quelle CASCADE")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(message)s")
    parser = argparse.ArgumentParser(description="Lädt einen Dump des operativen Systems ins Biofood-DWH")
    parser.add_argument("dump", help="z. B. data/dumps/biofood_oltp_2024-12-31.sql.gz")
    args = parser.parse_args()

    start = time.time()
    log.info("Starte ETL für %s", args.dump)
    extract(args.dump)
    log.info("Dump in Schema quelle wiederhergestellt (%.0f s)", time.time() - start)
    transform_load()
    log.info("Lauf erfolgreich in %.0f s", time.time() - start)


if __name__ == "__main__":
    main()
