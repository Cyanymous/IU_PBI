"""T – Transform: bringt die Extrakte in die Struktur der DWH-Tabellen."""

from datetime import date, timedelta

import pandas as pd

MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September",
          "Oktober", "November", "Dezember"]
WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


def filialen(df):
    """filialen.csv -> dim_filiale (bundesland_nr wird nicht gebraucht, steckt im Code)."""
    return df[["filiale_id", "filiale", "bundesland", "ort"]]


def artikel(df):
    """artikel.csv -> dim_sku, Warengruppe wird zur Kategorie."""
    return pd.DataFrame({
        "artikelnummer": df["artikelnummer"].astype(int),
        "artikelname": df["artikelname"],
        "stueckpreis": pd.to_numeric(df["stueckpreis"]),
        "kategorie_nr": df["warengruppe_nr"].astype(int),
        "kategorie_name": df["warengruppe"],
    })


def positionen(df):
    """pos_*.csv -> Zeilen für die Staging-Tabelle.

    Gibt (DataFrame, Anzahl verworfener Zeilen) zurück. Verworfen werden Zeilen,
    die keine echten Verkäufe sind (Modus ungleich prod oder Typ ungleich SALE).
    """
    gueltig = (df["Modus"] == "prod") & (df["Typ"] == "SALE")
    df = df[gueltig]
    zeit = pd.to_datetime(df["Datum"], format="%Y-%m-%d %H:%M:%S")
    out = pd.DataFrame({
        "filiale_id": df["Standort"],
        "kauf_nr": df["Referenz"].str.rsplit("-", n=1).str[1].astype(int),  # 05-10-0051052 -> 51052
        "artikelnummer": df["SKU"].astype(int),
        "datum_key": zeit.dt.year * 10000 + zeit.dt.month * 100 + zeit.dt.day,  # YYYYMMDD
        "anzahl": df["Mng"].astype(int),
    })
    return out, int((~gueltig).sum())


def datum(min_key, max_key):
    """Kalender für dim_datum: alle Tage der vollständigen Jahre zwischen min_key und max_key."""
    tag, ende = date(min_key // 10000, 1, 1), date(max_key // 10000, 12, 31)
    zeilen = []
    while tag <= ende:
        quartal = (tag.month - 1) // 3 + 1
        zeilen.append({
            "datum_key": tag.year * 10000 + tag.month * 100 + tag.day,
            "datum": tag,
            "datum_text": tag.strftime("%d.%m.%Y"),
            "jahr": tag.year,
            "quartal": quartal,
            "jahr_quartal": f"{tag.year}-Q{quartal}",
            "monat_nr": tag.month,
            "monat_name": MONATE[tag.month - 1],
            "jahr_monat": f"{tag.year}-{tag.month:02d}",
            "kw": tag.isocalendar().week,
            "tag_im_monat": tag.day,
            "tag_im_jahr": tag.timetuple().tm_yday,
            "wochentag_nr": tag.isoweekday(),          # 1 = Montag
            "wochentag_name": WOCHENTAGE[tag.weekday()],
        })
        tag += timedelta(days=1)
    return zeilen
