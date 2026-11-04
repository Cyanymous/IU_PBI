# Erzeugt Beispieldaten der operativen Biofood-Datenbank (ER-Modell) und sichert sie als Database Dump.
# Durch den festen SEED entstehen immer dieselben Daten.
#
# Ablauf: temporäre Datenbank biofood_oltp anlegen, Daten laden, pg_dump ausführen, Datenbank wieder löschen.
# Es entstehen zwei Dumps, jeweils der vollständige Stand der Datenbank an einem Stichtag:
#   Stand 2024-12-31: Einkäufe 2021-2024    -> Erstbeladung
#   Stand 2025-12-31: Einkäufe 2021-2025    -> Historie wächst, Vorhandenes wird überschrieben
#
# Einmalige Einrichtung im Projektordner:
#   python3 -m venv .venv && .venv/bin/pip install -r datagen/requirements.txt
# Aufruf im Projektordner (Container db muss laufen):
#   .venv/bin/python datagen/generate_source_data.py

# Libraries
import random
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import URL, create_engine, text

# Konstanten
SEED = 42
PROJEKT = Path(__file__).resolve().parent.parent
OUT = PROJEKT / "data" / "dumps"
OLTP_DB = "biofood_oltp"
SCHEMA = "quelle"

# Stichtag des Dumps -> Jahre, die seit dem vorherigen Stichtag dazugekommen sind
STAENDE = {"2024-12-31": range(2021, 2025), "2025-12-31": range(2025, 2026)}

# Tabellen genau nach ER-Modell (Spaltennamen ohne Umlaute)
DDL = f"""
CREATE SCHEMA {SCHEMA};
CREATE TABLE {SCHEMA}.kategorie (
    kategorie_nr   INTEGER PRIMARY KEY,
    kategorie_name VARCHAR(100) NOT NULL
);
CREATE TABLE {SCHEMA}.artikel (
    artikel_nr   INTEGER PRIMARY KEY,
    artikel_name VARCHAR(100) NOT NULL,
    stueckpreis  NUMERIC(10,2) NOT NULL,
    kategorie_nr INTEGER NOT NULL REFERENCES {SCHEMA}.kategorie
);
CREATE TABLE {SCHEMA}.filiale (
    filial_id  INTEGER PRIMARY KEY,
    bundesland VARCHAR(50)  NOT NULL,
    ort        VARCHAR(100) NOT NULL
);
CREATE TABLE {SCHEMA}.einkauf (
    kauf_nr   INTEGER PRIMARY KEY,
    kaufdatum DATE    NOT NULL,
    filial_id INTEGER NOT NULL REFERENCES {SCHEMA}.filiale
);
CREATE TABLE {SCHEMA}.einkauf_artikel (
    kauf_nr    INTEGER NOT NULL REFERENCES {SCHEMA}.einkauf,
    artikel_nr INTEGER NOT NULL REFERENCES {SCHEMA}.artikel,
    anzahl     INTEGER NOT NULL CHECK (anzahl > 0),
    PRIMARY KEY (kauf_nr, artikel_nr)
);
"""

# --------------------------------------------------------------------------
# Bundesländer mit ihren Filialen. Jeder Eintrag in der Städteliste ist eine Filiale,
# eine Stadt mit mehreren Filialen steht mehrfach in der Liste. Summe = 130 Filialen.
# --------------------------------------------------------------------------
BUNDESLAENDER = {
    "Schleswig-Holstein": ["Kiel", "Lübeck", "Flensburg", "Neumünster", "Norderstedt"],
    "Hamburg": ["Hamburg"] * 4,
    "Niedersachsen": ["Hannover", "Hannover", "Braunschweig", "Braunschweig", "Oldenburg", "Oldenburg",
                      "Osnabrück", "Göttingen", "Wolfsburg", "Hildesheim", "Lüneburg", "Celle"],
    "Bremen": ["Bremen", "Bremerhaven"],
    "Nordrhein-Westfalen": ["Köln", "Köln", "Düsseldorf", "Düsseldorf", "Dortmund", "Dortmund",
                            "Essen", "Essen", "Münster", "Münster", "Bonn", "Bonn", "Bielefeld",
                            "Bielefeld", "Aachen", "Aachen", "Bochum", "Bochum", "Wuppertal", "Wuppertal",
                            "Duisburg", "Gelsenkirchen", "Paderborn", "Krefeld", "Mönchengladbach"],
    "Hessen": ["Frankfurt am Main", "Frankfurt am Main", "Wiesbaden", "Wiesbaden", "Kassel", "Kassel",
               "Darmstadt", "Offenbach am Main", "Marburg", "Gießen"],
    "Rheinland-Pfalz": ["Mainz", "Mainz", "Koblenz", "Koblenz", "Trier", "Kaiserslautern",
                        "Ludwigshafen am Rhein"],
    "Baden-Württemberg": ["Stuttgart", "Stuttgart", "Freiburg im Breisgau", "Freiburg im Breisgau",
                          "Karlsruhe", "Karlsruhe", "Mannheim", "Mannheim", "Heidelberg", "Heidelberg",
                          "Tübingen", "Tübingen", "Ulm", "Konstanz", "Heilbronn", "Pforzheim"],
    "Bayern": ["München", "München", "Nürnberg", "Nürnberg", "Augsburg", "Augsburg", "Regensburg",
               "Regensburg", "Würzburg", "Würzburg", "Ingolstadt", "Ingolstadt", "Erlangen", "Erlangen",
               "Bamberg", "Bamberg", "Rosenheim", "Passau", "Landshut"],
    "Saarland": ["Saarbrücken", "Neunkirchen"],
    "Berlin": ["Berlin"] * 6,
    "Brandenburg": ["Potsdam", "Cottbus", "Frankfurt (Oder)", "Brandenburg an der Havel"],
    "Mecklenburg-Vorpommern": ["Rostock", "Schwerin", "Greifswald"],
    "Sachsen": ["Leipzig", "Leipzig", "Dresden", "Dresden", "Chemnitz", "Zwickau", "Görlitz"],
    "Sachsen-Anhalt": ["Halle (Saale)", "Halle (Saale)", "Magdeburg", "Dessau-Roßlau"],
    "Thüringen": ["Erfurt", "Jena", "Weimar", "Gera"],
}

# --------------------------------------------------------------------------
# Kategorien: Nr -> (Name, Basisgewicht Kaufhäufigkeit, Trend pro Jahr)
# --------------------------------------------------------------------------
KATEGORIEN = {
    1: ("Obst & Gemüse", 0.20, 0.02),
    2: ("Molkereiprodukte & Eier", 0.16, 0.01),
    3: ("Backwaren", 0.12, 0.02),
    4: ("Trockensortiment", 0.13, 0.03),
    5: ("Getränke", 0.10, 0.01),
    6: ("Fleisch, Wurst & Fisch", 0.06, -0.05),
    7: ("Vegetarisch & Vegan", 0.07, 0.15),
    8: ("Süßwaren & Snacks", 0.08, 0.02),
    9: ("Drogerie & Naturkosmetik", 0.05, 0.06),
    10: ("Haushalt & Reinigung", 0.03, 0.03),
}

# Artikel je Kategorie: (Name, Stückpreis in Cent)
ARTIKEL = {
    1: [("Bio Äpfel Elstar 1 kg", 349), ("Bio Bananen 1 kg", 249), ("Bio Karotten 1 kg", 199),
        ("Bio Tomaten 500 g", 299), ("Bio Kartoffeln festkochend 2 kg", 399)],
    2: [("Bio Vollmilch 3,8 % 1 l", 159), ("Bio Joghurt natur 500 g", 149), ("Bio Butter 250 g", 349),
        ("Bio Eier 10 Stück", 499), ("Bio Gouda jung 200 g", 329)],
    3: [("Bio Dinkelvollkornbrot 750 g", 469), ("Bio Roggenmischbrot 1 kg", 449),
        ("Bio Weizenbrötchen Stück", 59), ("Bio Laugenbrezel Stück", 89), ("Bio Croissant Stück", 129)],
    4: [("Bio Spaghetti 500 g", 169), ("Bio Basmatireis 1 kg", 449), ("Bio Haferflocken zart 500 g", 129),
        ("Bio Olivenöl nativ extra 500 ml", 999), ("Bio Röstkaffee Bohne 500 g", 1099)],
    5: [("Bio Apfelsaft naturtrüb 1 l", 249), ("Mineralwasser still 0,75 l", 99),
        ("Bio Haferdrink 1 l", 199), ("Bio Rotwein Spanien 0,75 l", 799), ("Bio Pils 0,5 l", 129)],
    6: [("Bio Hähnchenbrustfilet 400 g", 1199), ("Bio Rinderhackfleisch 400 g", 799),
        ("Bio Salami geschnitten 80 g", 349), ("Bio Kochschinken 100 g", 329), ("Bio Lachsfilet 250 g", 899)],
    7: [("Bio Tofu natur 400 g", 279), ("Bio Tempeh 200 g", 349), ("Bio Veggie-Burger 2 Stück", 399),
        ("Bio Falafel 220 g", 349), ("Bio Hummus natur 175 g", 229)],
    8: [("Bio Zartbitterschokolade 70 % 100 g", 229), ("Bio Kartoffelchips Meersalz 125 g", 229),
        ("Bio Studentenfutter 200 g", 399), ("Bio Fruchtgummi 100 g", 199),
        ("Bio Dinkel-Butterkekse 200 g", 219)],
    9: [("Naturkosmetik Duschgel 250 ml", 349), ("Naturkosmetik Shampoo 200 ml", 449),
        ("Naturkosmetik Handcreme 75 ml", 499), ("Naturkosmetik Zahncreme 75 ml", 299),
        ("Naturkosmetik Deo Roller 50 ml", 399)],
    10: [("Öko Spülmittel 500 ml", 249), ("Öko Waschmittel flüssig 1,5 l", 899),
         ("Öko Allzweckreiniger 500 ml", 299), ("Recycling-Toilettenpapier 8 Rollen", 449),
         ("Öko Spülmaschinentabs 25 Stück", 599)],
}

# Saisonfaktor Kundenfrequenz je Monat (Index 0 = Januar)
SAISON_FREQUENZ = [0.92, 0.94, 0.98, 1.00, 1.00, 1.02, 1.00, 0.97, 1.00, 1.01, 1.03, 1.15]
# Kundenfrequenz-Entwicklung je Jahr
JAHRESFAKTOR = {2021: 1.00, 2022: 0.95, 2023: 0.99, 2024: 1.04, 2025: 1.08}
# Wochentag 0=Mo ... 5=Sa
WOCHENTAG = [0.90, 0.90, 0.95, 1.00, 1.15, 1.25]
BASIS_EINKAEUFE_PRO_TAG = 27
POSITIONEN = [1, 2, 3, 4, 5, 6, 7, 8]
POSITIONEN_GEWICHT = [0.14, 0.18, 0.19, 0.16, 0.12, 0.09, 0.07, 0.05]


# Verbindung zu einer Datenbank im Container db, Zugangsdaten aus der Datei .env
def verbindung(datenbank):
    zeilen = (PROJEKT / ".env").read_text().splitlines()
    env = dict(z.split("=", 1) for z in zeilen if "=" in z and not z.startswith("#"))
    url = URL.create("postgresql+psycopg2", username=env["DB_USER"], password=env["DB_PASSWORD"],
                     host="localhost", port=5432, database=datenbank)
    return create_engine(url, isolation_level="AUTOCOMMIT")


# Hängt die Zeilen einer Python-Liste an eine Tabelle der Quelldatenbank an
def lade_tabelle(engine, tabelle, spalten, zeilen):
    df = pd.DataFrame(zeilen, columns=spalten)
    df.to_sql(tabelle, engine, schema=SCHEMA, if_exists="append", index=False, chunksize=100_000)


# gibt die Feiertage eines Jahres als date zurück
def feiertage(jahr):
    return {date(jahr, 1, 1), date(jahr, 5, 1), date(jahr, 10, 3), date(jahr, 12, 25), date(jahr, 12, 26)}


# gibt alle Verkaufstage eines Jahres als date zurück (Mo-Sa ohne Feiertage)
def verkaufstage(jahr):
    ft = feiertage(jahr)
    tag = date(jahr, 1, 1)
    while tag.year == jahr:
        if tag.weekday() < 6 and tag not in ft:
            yield tag
        tag += timedelta(days=1)


# Artikelstamm mit ArtikelNr = KategorieNr * 1000 + laufende Nr.
def baue_artikel(rnd):
    artikel = []
    for kat, liste in ARTIKEL.items():
        for n, (name, preis) in enumerate(liste, start=1):
            artikel.append({"nr": kat * 1000 + n, "name": name, "preis": preis, "kat": kat,
                            "beliebtheit": rnd.lognormvariate(0, 0.5)})
    return artikel


# Eine Filiale je Eintrag in der Städteliste, FilialID fortlaufend
def baue_filialen(rnd):
    filialen = []
    for land, orte in BUNDESLAENDER.items():
        for ort in orte:
            filialen.append({"id": len(filialen) + 1, "land": land, "ort": ort,
                             "groesse": min(1.6, max(0.6, rnd.lognormvariate(0, 0.25)))})
    return filialen


# Kumulierte Artikelgewichte eines Jahres (Kategorie-Anteil, Trend, Beliebtheit)
def gewichte(artikel, jahr):
    kum, summe = [], 0.0
    for a in artikel:
        basis, trend = KATEGORIEN[a["kat"]][1:]
        summe += basis * (1 + trend) ** (jahr - 2021) * a["beliebtheit"] / len(ARTIKEL[a["kat"]])
        kum.append(summe)
    return kum


# Reihenfolge wegen der Fremdschlüssel: erst Kategorien, dann die Artikel, die darauf verweisen
def lade_stammdaten(engine, artikel, filialen):
    lade_tabelle(engine, "kategorie", ["kategorie_nr", "kategorie_name"],
                 [(nr, werte[0]) for nr, werte in KATEGORIEN.items()])
    lade_tabelle(engine, "artikel", ["artikel_nr", "artikel_name", "stueckpreis", "kategorie_nr"],
                 [(a["nr"], a["name"], a["preis"] / 100, a["kat"]) for a in artikel])
    lade_tabelle(engine, "filiale", ["filial_id", "bundesland", "ort"],
                 [(fil["id"], fil["land"], fil["ort"]) for fil in filialen])


# Erzeugt alle Einkäufe der angegebenen Jahre und lädt sie Jahr für Jahr in die Quelldatenbank.
# Gibt die letzte vergebene KaufNr sowie Anzahl Positionen und Umsatz in Cent zurück.
def lade_einkaeufe(engine, jahre, kauf_nr, artikel, filialen, rnd):
    zeilen = umsatz = 0
    for jahr in jahre:
        einkaeufe, positionen = [], []
        kum = gewichte(artikel, jahr)
        for tag in verkaufstage(jahr):
            for fil in filialen:
                erwartung = (BASIS_EINKAEUFE_PRO_TAG * fil["groesse"] * JAHRESFAKTOR[jahr]
                             * SAISON_FREQUENZ[tag.month - 1] * WOCHENTAG[tag.weekday()])
                for _ in range(round(erwartung * rnd.uniform(0.8, 1.2))):   # Erwartungswert ±20 %
                    kauf_nr += 1
                    einkaeufe.append((kauf_nr, tag, fil["id"]))
                    k = rnd.choices(POSITIONEN, POSITIONEN_GEWICHT)[0]
                    gewaehlt = set()
                    while len(gewaehlt) < k:   # jeder Artikel nur einmal pro Einkauf
                        a = rnd.choices(artikel, cum_weights=kum)[0]
                        if a["nr"] not in gewaehlt:
                            gewaehlt.add(a["nr"])
                            anzahl = rnd.choices([1, 2, 3], [0.75, 0.18, 0.07])[0]
                            positionen.append((kauf_nr, a["nr"], anzahl))
                            zeilen += 1
                            umsatz += anzahl * a["preis"]
        # Reihenfolge wegen der Fremdschlüssel: erst Einkäufe, dann ihre Artikel
        lade_tabelle(engine, "einkauf", ["kauf_nr", "kaufdatum", "filial_id"], einkaeufe)
        lade_tabelle(engine, "einkauf_artikel", ["kauf_nr", "artikel_nr", "anzahl"], positionen)
        print(f"  {jahr}: {len(einkaeufe)} Einkäufe, {len(positionen)} Positionen geladen", flush=True)
    return kauf_nr, zeilen, umsatz


# Echter pg_dump (Klartext-SQL, gzip-komprimiert) des aktuellen Stands der Quelldatenbank
def dump(stand):
    ziel = OUT / f"{OLTP_DB}_{stand}.sql.gz"
    befehl = f'pg_dump -U "$POSTGRES_USER" -d {OLTP_DB} -n {SCHEMA} --no-owner --no-privileges -Z 6'
    with open(ziel, "wb") as f:
        subprocess.run(["docker", "compose", "exec", "-T", "db", "sh", "-c", befehl],
                       cwd=PROJEKT, stdout=f, check=True)
    return ziel


def main():
    rnd = random.Random(SEED)
    artikel = baue_artikel(rnd)
    filialen = baue_filialen(rnd)
    OUT.mkdir(parents=True, exist_ok=True)

    # Temporäre Quelldatenbank anlegen
    admin = verbindung("postgres")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {OLTP_DB}"))
        conn.execute(text(f"CREATE DATABASE {OLTP_DB}"))
    engine = verbindung(OLTP_DB)
    with engine.connect() as conn:
        conn.execute(text(DDL))

    lade_stammdaten(engine, artikel, filialen)
    kauf_nr = zeilen_gesamt = umsatz_gesamt = 0
    for stand, jahre in STAENDE.items():
        kauf_nr, zeilen, umsatz = lade_einkaeufe(engine, jahre, kauf_nr, artikel, filialen, rnd)
        zeilen_gesamt += zeilen
        umsatz_gesamt += umsatz
        ziel = dump(stand)
        print(f"Stand {stand}: {kauf_nr} Einkäufe, {zeilen_gesamt} Positionen, "
              f"Umsatz {umsatz_gesamt / 100:.2f} EUR -> {ziel.name} ({ziel.stat().st_size / 1e6:.0f} MB)",
              flush=True)

    # Das operative System existiert ab jetzt nur noch in Form der Dumps
    engine.dispose()
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE {OLTP_DB}"))


if __name__ == "__main__":
    main()
