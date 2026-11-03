"""E – Extract: liest die CSV-Extrakte des Kassensystems unverändert als Text ein."""

from pathlib import Path

import pandas as pd

# Nur die Spalten der Kassendaten, die das DWH braucht
POS_SPALTEN = ["Referenz", "Datum", "Standort", "Modus", "Typ", "Mng", "SKU"]


def lese_filialen(ordner):
    return pd.read_csv(Path(ordner) / "filialen.csv", sep=";", dtype=str)


def lese_artikel(ordner):
    return pd.read_csv(Path(ordner) / "artikel.csv", sep=";", dtype=str)


def pos_dateien(ordner):
    dateien = sorted(Path(ordner).glob("pos_*.csv"))
    if not dateien:
        raise FileNotFoundError(f"Keine pos_*.csv in {ordner}")
    return dateien


def lese_pos(datei):
    return pd.read_csv(datei, sep=";", usecols=POS_SPALTEN, dtype=str)
