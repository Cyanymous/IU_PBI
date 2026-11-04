"""Richtet die Datenbasis in Superset ein (REST-API, wiederholbar).

Legt an bzw. aktualisiert:
  1. Datenbankverbindung "Biofood DWH" (User superset_ro, nur SELECT)
  2. Virtuelles Dataset "v_verkauf" (SQL liegt in Superset, nicht im DWH) mit Metriken
Charts und Dashboards werden im Browser gebaut.

Aufruf:  docker compose exec superset python /app/superset_config/provision.py
Achtung: Änderungen, die im Browser an diesen Objekten gemacht wurden, werden überschrieben.
"""

import json
import os

import requests

BASIS = "http://localhost:8088/api/v1"
DB_NAME = "Biofood DWH"
DATASET = "v_verkauf"

# Virtuelles Dataset: Fakten mit allen drei Dimensionen, Umsatz = Anzahl * Stückpreis
DATASET_SQL = """SELECT d.datum,
       d.jahr,
       'Q' || d.quartal          AS quartal,
       d.jahr_quartal,
       d.monat_nr,
       d.monat_name,
       d.jahr_monat,
       l.filiale_id,
       l.bundesland,
       l.ort,
       s.artikelnummer,
       s.artikelname,
       s.kategorie_nr,
       s.kategorie_name,
       s.stueckpreis,
       f.kauf_nr,
       f.anzahl,
       f.anzahl * s.stueckpreis  AS umsatz
  FROM fakt_verkauf f
  JOIN dim_datum   d USING (datum_key)
  JOIN dim_sku     s USING (artikelnummer_key)
  JOIN dim_filiale l USING (filiale_key)"""

SPALTEN_DE = {
    "datum": "Datum", "jahr": "Jahr", "quartal": "Quartal", "jahr_quartal": "Jahr-Quartal",
    "monat_nr": "Monat (Nr.)", "monat_name": "Monat", "jahr_monat": "Jahr-Monat",
    "filiale_id": "Filial-ID", "bundesland": "Bundesland", "ort": "Ort",
    "artikelnummer": "Artikelnummer", "artikelname": "Artikel", "kategorie_nr": "Kategorie-Nr.",
    "kategorie_name": "Kategorie", "stueckpreis": "Stückpreis", "kauf_nr": "Kauf-Nr.",
    "anzahl": "Anzahl", "umsatz": "Umsatz (Position)",
}

METRIKEN = [
    {"metric_name": "umsatz", "verbose_name": "Umsatz", "expression": "SUM(umsatz)", "d3format": "$,.2f"},
    {"metric_name": "stueck", "verbose_name": "Verkaufte Stück", "expression": "SUM(anzahl)", "d3format": ",d"},
]

class Api:
    """Kleine Hülle um die Superset-REST-API (JWT + CSRF-Token)."""

    def __init__(self):
        self.s = requests.Session()
        r = self.s.post(f"{BASIS}/security/login", json={
            "username": "admin", "password": os.environ["SUPERSET_ADMIN_PASSWORD"],
            "provider": "db", "refresh": True})
        r.raise_for_status()
        self.s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        csrf = self.s.get(f"{BASIS}/security/csrf_token/")
        csrf.raise_for_status()
        self.s.headers["X-CSRFToken"] = csrf.json()["result"]
        self.s.headers["Referer"] = BASIS

    def _pruefe(self, r):
        if not r.ok:
            raise RuntimeError(f"{r.request.method} {r.url} -> {r.status_code}: {r.text[:800]}")
        return r.json() if r.text else {}

    def get(self, pfad, **kw):
        return self._pruefe(self.s.get(f"{BASIS}/{pfad}", **kw))

    def post(self, pfad, daten):
        return self._pruefe(self.s.post(f"{BASIS}/{pfad}", json=daten))

    def put(self, pfad, daten=None):
        return self._pruefe(self.s.put(f"{BASIS}/{pfad}", json=daten))

    def finde(self, ressource, feld, wert):
        """ID des Objekts mit feld == wert oder None (Listen sind hier klein)."""
        ergebnis = self.get(f"{ressource}/", params={"q": "(page_size:100)"})["result"]
        treffer = [o["id"] for o in ergebnis if o.get(feld) == wert]
        return treffer[0] if treffer else None

    def upsert(self, ressource, feld, wert, daten):
        oid = self.finde(ressource, feld, wert)
        if oid is None:
            oid = self.post(f"{ressource}/", daten)["id"]
            print(f"  angelegt:     {ressource} '{wert}' (id {oid})")
        else:
            self.put(f"{ressource}/{oid}", daten)
            print(f"  aktualisiert: {ressource} '{wert}' (id {oid})")
        return oid


def datenbank(api):
    uri = f"postgresql+psycopg2://superset_ro:{os.environ['SUPERSET_RO_PASSWORD']}@db:5432/biofood_dwh"
    return api.upsert("database", "database_name", DB_NAME, {
        "database_name": DB_NAME, "sqlalchemy_uri": uri, "expose_in_sqllab": True})


def dataset(api, db_id):
    ds_id = api.finde("dataset", "table_name", DATASET)
    if ds_id is None:
        ds_id = api.post("dataset/", {"database": db_id, "schema": "public",
                                      "table_name": DATASET, "sql": DATASET_SQL})["id"]
        print(f"  angelegt:     dataset '{DATASET}' (id {ds_id})")
    else:
        api.put(f"dataset/{ds_id}", {"sql": DATASET_SQL})
        print(f"  aktualisiert: dataset '{DATASET}' (id {ds_id})")
    api.put(f"dataset/{ds_id}/refresh")            # Spalten aus dem SQL übernehmen

    aktuell = api.get(f"dataset/{ds_id}")["result"]
    spalten = [{"id": c["id"], "column_name": c["column_name"],
                "verbose_name": SPALTEN_DE.get(c["column_name"]),
                "is_dttm": c["column_name"] == "datum",
                "groupby": True, "filterable": True}
               for c in aktuell["columns"]]
    vorhandene = {m["metric_name"]: m["id"] for m in aktuell["metrics"]}
    metriken = [dict(m, **({"id": vorhandene[m["metric_name"]]} if m["metric_name"] in vorhandene else {}))
                for m in METRIKEN]
    api.put(f"dataset/{ds_id}", {"main_dttm_col": "datum", "columns": spalten, "metrics": metriken,
                                 "description": "Fakten mit Datum, Filiale und Artikel (virtuell)"})
    return ds_id


def main():
    api = Api()
    print("1. Datenbankverbindung")
    db_id = datenbank(api)
    print("2. Virtuelles Dataset")
    dataset(api, db_id)
    print("Fertig: Dataset 'v_verkauf' steht für Charts bereit.")


if __name__ == "__main__":
    main()
