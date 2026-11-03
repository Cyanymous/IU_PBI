"""Orchestrierung des ETL-Laufs: Extract -> Transform -> Load für einen Extrakt-Ordner.

Aufruf:  python main.py data/source/2021-2024
Ein Lauf = eine Transaktion. Bei einem Fehler wird alles zurückgerollt.
Reihenfolge: erst Dimensionen (Filiale, SKU, Datum), dann Fakten.
"""

import argparse
import logging
import sys
import time

import extract
import load
import transform

log = logging.getLogger("etl")


def lauf(ordner):
    start = time.time()
    with load.engine().begin() as conn:      # eine Transaktion pro Lauf
        # Dimensionen aus den Stammdaten
        filialen = transform.filialen(extract.lese_filialen(ordner))
        load.dim_filiale(conn, filialen)
        log.info("dim_filiale: %d Filialen geladen", len(filialen))

        artikel = transform.artikel(extract.lese_artikel(ordner))
        load.dim_sku(conn, artikel)
        log.info("dim_sku: %d Artikel geladen", len(artikel))

        # Kassendaten Datei für Datei in die Staging-Tabelle
        load.erstelle_staging(conn)
        zeilen = verworfen = 0
        min_key, max_key = 99999999, 0
        dateien = extract.pos_dateien(ordner)
        for datei in dateien:
            pos, weg = transform.positionen(extract.lese_pos(datei))
            load.staging(conn, pos)
            zeilen += len(pos)
            verworfen += weg
            if len(pos):
                min_key = min(min_key, int(pos["datum_key"].min()))
                max_key = max(max_key, int(pos["datum_key"].max()))
        log.info("Staging: %d Positionen aus %d Dateien, %d verworfen (kein prod/SALE)",
                 zeilen, len(dateien), verworfen)
        if zeilen == 0:
            raise ValueError("Keine gültigen Positionen gefunden")

        # Datumsdimension passend zu den Kaufdaten (ganze Jahre)
        kalender = transform.datum(min_key, max_key)
        load.dim_datum(conn, kalender)
        log.info("dim_datum: %d Tage (%s bis %s)", len(kalender), kalender[0]["datum"], kalender[-1]["datum"])

        # Datenqualität: Positionen ohne passende Dimension -> Abbruch
        fehlend = load.unbekannte_schluessel(conn)
        if fehlend:
            for f in fehlend[:10]:
                log.error("Unbekannt: Filiale %s / Artikel %s (%d Zeilen)", *f)
            raise ValueError(f"{len(fehlend)} unbekannte Filiale/Artikel-Kombinationen")

        # Fakten
        neu, ueberschrieben = load.fakt_verkauf(conn)
        log.info("fakt_verkauf: %d neu, %d überschrieben", neu, ueberschrieben)
    log.info("Lauf erfolgreich in %.0f s", time.time() - start)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(message)s")
    parser = argparse.ArgumentParser(description="Lädt einen Extrakt-Ordner ins Biofood-DWH")
    parser.add_argument("ordner", help="z. B. data/source/2021-2024")
    args = parser.parse_args()
    log.info("Starte ETL für %s", args.ordner)
    try:
        lauf(args.ordner)
    except Exception:
        log.exception("Lauf abgebrochen, Transaktion zurückgerollt")
        sys.exit(1)


if __name__ == "__main__":
    main()
