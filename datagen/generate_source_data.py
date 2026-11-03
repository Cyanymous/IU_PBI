# Skript zum dynamischen Generieren der Daten für DWH
# Daten werden durch festgelegten SEED immer gleich generiiert
# Für jede Filiale wird eine einzelne csv Datei generiert

# Libraries
import csv
import random
from datetime import date, datetime, timedelta
from multiprocessing import Pool
from pathlib import Path

# Konstanten
SEED = 42
START = date(2021, 1, 1)
END = date(2025, 12, 31)

# Splitten der Datei ermöglicht das Teste von Überschreiben der Daten und nur neue Daten einlesen
SPLITS = {"2021-2024": range(2021, 2025), "2025": range(2025, 2026)}
OUT = Path(__file__).resolve().parent.parent / "data" / "source"

# --------------------------------------------------------------------------
# Bundesländer: ID -> (Name, Städte mit Filiale). Jeder Eintrag ist eine Filiale,
# eine Stadt mit mehreren Filialen steht mehrfach in der Liste. Summe = 130 Filialen.
# --------------------------------------------------------------------------
BUNDESLAENDER = {
    1: ("Schleswig-Holstein", ["Kiel", "Lübeck", "Flensburg", "Neumünster", "Norderstedt"]),
    2: ("Hamburg", ["Hamburg"] * 4),
    3: ("Niedersachsen", ["Hannover", "Hannover", "Braunschweig", "Braunschweig", "Oldenburg", "Oldenburg",
                          "Osnabrück", "Göttingen", "Wolfsburg", "Hildesheim", "Lüneburg", "Celle"]),
    4: ("Bremen", ["Bremen", "Bremerhaven"]),
    5: ("Nordrhein-Westfalen", ["Köln", "Köln", "Düsseldorf", "Düsseldorf", "Dortmund", "Dortmund",
                                "Essen", "Essen", "Münster", "Münster", "Bonn", "Bonn", "Bielefeld",
                                "Bielefeld", "Aachen", "Aachen", "Bochum", "Bochum", "Wuppertal", "Wuppertal",
                                "Duisburg", "Gelsenkirchen", "Paderborn", "Krefeld", "Mönchengladbach"]),
    6: ("Hessen", ["Frankfurt am Main", "Frankfurt am Main", "Wiesbaden", "Wiesbaden", "Kassel", "Kassel",
                   "Darmstadt", "Offenbach am Main", "Marburg", "Gießen"]),
    7: ("Rheinland-Pfalz", ["Mainz", "Mainz", "Koblenz", "Koblenz", "Trier", "Kaiserslautern",
                            "Ludwigshafen am Rhein"]),
    8: ("Baden-Württemberg", ["Stuttgart", "Stuttgart", "Freiburg im Breisgau", "Freiburg im Breisgau",
                              "Karlsruhe", "Karlsruhe", "Mannheim", "Mannheim", "Heidelberg", "Heidelberg",
                              "Tübingen", "Tübingen", "Ulm", "Konstanz", "Heilbronn", "Pforzheim"]),
    9: ("Bayern", ["München", "München", "Nürnberg", "Nürnberg", "Augsburg", "Augsburg", "Regensburg",
                   "Regensburg", "Würzburg", "Würzburg", "Ingolstadt", "Ingolstadt", "Erlangen", "Erlangen",
                   "Bamberg", "Bamberg", "Rosenheim", "Passau", "Landshut"]),
    10: ("Saarland", ["Saarbrücken", "Neunkirchen"]),
    11: ("Berlin", ["Berlin"] * 6),
    12: ("Brandenburg", ["Potsdam", "Cottbus", "Frankfurt (Oder)", "Brandenburg an der Havel"]),
    13: ("Mecklenburg-Vorpommern", ["Rostock", "Schwerin", "Greifswald"]),
    14: ("Sachsen", ["Leipzig", "Leipzig", "Dresden", "Dresden", "Chemnitz", "Zwickau", "Görlitz"]),
    15: ("Sachsen-Anhalt", ["Halle (Saale)", "Halle (Saale)", "Magdeburg", "Dessau-Roßlau"]),
    16: ("Thüringen", ["Erfurt", "Jena", "Weimar", "Gera"]),
}

# --------------------------------------------------------------------------
# Warengruppen: Nr -> (Name, Basisgewicht Kaufhäufigkeit, Trend pro Jahr)
# --------------------------------------------------------------------------
WARENGRUPPEN = {
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

# Artikel je Warengruppe: (Name, Bruttopreis in Cent, Steuersatz in %)
ARTIKEL = {
    1: [("Bio Äpfel Elstar 1 kg", 349, 7), ("Bio Bananen 1 kg", 249, 7), ("Bio Karotten 1 kg", 199, 7),
        ("Bio Tomaten 500 g", 299, 7), ("Bio Kartoffeln festkochend 2 kg", 399, 7)],
    2: [("Bio Vollmilch 3,8 % 1 l", 159, 7), ("Bio Joghurt natur 500 g", 149, 7), ("Bio Butter 250 g", 349, 7),
        ("Bio Eier 10 Stück", 499, 7), ("Bio Gouda jung 200 g", 329, 7)],
    3: [("Bio Dinkelvollkornbrot 750 g", 469, 7), ("Bio Roggenmischbrot 1 kg", 449, 7),
        ("Bio Weizenbrötchen Stück", 59, 7), ("Bio Laugenbrezel Stück", 89, 7), ("Bio Croissant Stück", 129, 7)],
    4: [("Bio Spaghetti 500 g", 169, 7), ("Bio Basmatireis 1 kg", 449, 7), ("Bio Haferflocken zart 500 g", 129, 7),
        ("Bio Olivenöl nativ extra 500 ml", 999, 7), ("Bio Röstkaffee Bohne 500 g", 1099, 7)],
    5: [("Bio Apfelsaft naturtrüb 1 l", 249, 19), ("Mineralwasser still 0,75 l", 99, 19),
        ("Bio Haferdrink 1 l", 199, 19), ("Bio Rotwein Spanien 0,75 l", 799, 19), ("Bio Pils 0,5 l", 129, 19)],
    6: [("Bio Hähnchenbrustfilet 400 g", 1199, 7), ("Bio Rinderhackfleisch 400 g", 799, 7),
        ("Bio Salami geschnitten 80 g", 349, 7), ("Bio Kochschinken 100 g", 329, 7), ("Bio Lachsfilet 250 g", 899, 7)],
    7: [("Bio Tofu natur 400 g", 279, 7), ("Bio Tempeh 200 g", 349, 7), ("Bio Veggie-Burger 2 Stück", 399, 7),
        ("Bio Falafel 220 g", 349, 7), ("Bio Hummus natur 175 g", 229, 7)],
    8: [("Bio Zartbitterschokolade 70 % 100 g", 229, 7), ("Bio Kartoffelchips Meersalz 125 g", 229, 7),
        ("Bio Studentenfutter 200 g", 399, 7), ("Bio Fruchtgummi 100 g", 199, 7),
        ("Bio Dinkel-Butterkekse 200 g", 219, 7)],
    9: [("Naturkosmetik Duschgel 250 ml", 349, 19), ("Naturkosmetik Shampoo 200 ml", 449, 19),
        ("Naturkosmetik Handcreme 75 ml", 499, 19), ("Naturkosmetik Zahncreme 75 ml", 299, 19),
        ("Naturkosmetik Deo Roller 50 ml", 399, 19)],
    10: [("Öko Spülmittel 500 ml", 249, 19), ("Öko Waschmittel flüssig 1,5 l", 899, 19),
         ("Öko Allzweckreiniger 500 ml", 299, 19), ("Recycling-Toilettenpapier 8 Rollen", 449, 19),
         ("Öko Spülmaschinentabs 25 Stück", 599, 19)],
}

# Saisonfaktor Kundenfrequenz je Monat (Index 0 = Januar)
SAISON_FREQUENZ = [0.92, 0.94, 0.98, 1.00, 1.00, 1.02, 1.00, 0.97, 1.00, 1.01, 1.03, 1.15]
# Kundenfrequenz-Entwicklung je Jahr
JAHRESFAKTOR = {2021: 1.00, 2022: 0.95, 2023: 0.99, 2024: 1.04, 2025: 1.08}
# Wochentag 0=Mo ... 5=Sa
WOCHENTAG = [0.90, 0.90, 0.95, 1.00, 1.15, 1.25]
# Öffnungszeiten 8-20 Uhr, Gewicht je Stunde
STUNDEN = list(range(8, 20))
STUNDEN_GEWICHT = [0.5, 0.7, 0.9, 1.0, 1.1, 0.9, 0.8, 0.9, 1.1, 1.4, 1.3, 0.8]
BASIS_EINKAEUFE_PRO_TAG = 27
POSITIONEN = [1, 2, 3, 4, 5, 6, 7, 8]
POSITIONEN_GEWICHT = [0.14, 0.18, 0.19, 0.16, 0.12, 0.09, 0.07, 0.05]

# Spalten der generierten CSV Dateien
POS_HEADER = ["ID", "Referenz", "Datum", "Standort", "Modus", "Kasse", "Mitarbeiter", "Typ", "Mng",
              "SKU", "Einzelpreis", "Finalpreis", "Artikelname", "Warengruppe", "SteuerName",
              "SteuerRate", "Vorsteuern", "SteuernMenge"]

# gibt die Daten für die Feiertage zurück als date zurück
def feiertage(jahr):
    return {date(jahr, 1, 1), date(jahr, 5, 1), date(jahr, 10, 3), date(jahr, 12, 25), date(jahr, 12, 26)}

# gibt alle verkaufstage im zeitraum von START und END als date zurück
def verkaufstage():
    ft = set().union(*(feiertage(j) for j in range(START.year, END.year + 1)))
    d = START
    while d <= END:
        if d.weekday() < 6 and d not in ft:
            yield d
        d += timedelta(days=1)

# Artikelstamm mit SKU = Warengruppe * 1000 + laufende Nr.
def baue_artikel():
    artikel = []
    rnd = random.Random(SEED)
    for wg, liste in ARTIKEL.items():
        for n, (name, preis, steuer) in enumerate(liste, start=1):
            artikel.append({"sku": wg * 1000 + n, "name": name, "preis": preis, "steuer": steuer,
                            "wg": wg, "beliebtheit": rnd.lognormvariate(0, 0.5)})
    return artikel

# Eine Filiale je Eintrag in der Städteliste, Code = Bundesland-Filialnummer.
def baue_filialen():
    rnd = random.Random(SEED + 1)
    filialen = []
    mitarbeiter_nr = 1001
    for bl, (land, orte) in BUNDESLAENDER.items():
        zaehler = {}
        for nr, ort in enumerate(orte, start=1):
            zaehler[ort] = zaehler.get(ort, 0) + 1
            name = f"Biofood {ort}" + (f" {zaehler[ort]}" if zaehler[ort] > 1 else "")
            groesse = min(1.6, max(0.6, rnd.lognormvariate(0, 0.25)))
            n_ma = 5 + round((groesse - 0.6) * 7)
            filialen.append({"code": f"{bl:02d}-{nr:02d}", "bl": bl, "name": name, "land": land, "ort": ort,
                             "groesse": groesse, "kassen": 2 if groesse < 0.9 else (3 if groesse < 1.25 else 4),
                             "mitarbeiter": list(range(mitarbeiter_nr, mitarbeiter_nr + n_ma))})
            mitarbeiter_nr += n_ma
    return filialen


def menge(rnd):
    """Stückzahl je Position: meist 1, seltener 2 oder 3."""
    return rnd.choices([1, 2, 3], [0.75, 0.18, 0.07])[0]


def cent(betrag):
    return f"{betrag // 100}.{betrag % 100:02d}"

# Kumulierte Artikelgewichte je Jahr (Warengruppen-Anteil, Trend, Beliebtheit).
def gewichte_je_jahr(artikel):
    tabelle = {}
    for jahr in range(START.year, END.year + 1):
        kum, s = [], 0.0
        for a in artikel:
            basis, trend = WARENGRUPPEN[a["wg"]][1], WARENGRUPPEN[a["wg"]][2]
            s += basis * (1 + trend) ** (jahr - START.year) * a["beliebtheit"] / len(ARTIKEL[a["wg"]])
            kum.append(s)
        tabelle[jahr] = kum
    return tabelle


def generiere_filiale(args):
    idx, fil, artikel, tage = args
    rnd = random.Random(SEED * 1000 + idx)
    gewichte = gewichte_je_jahr(artikel)
    kassen = [f"Kasse {k}" for k in range(1, fil["kassen"] + 1)]
    wg_namen = {wg: v[0] for wg, v in WARENGRUPPEN.items()}

    dateien, writer = {}, {}
    for teil in SPLITS:
        f = open(OUT / teil / f"pos_{fil['code']}.csv", "w", newline="", encoding="utf-8")
        dateien[teil] = f
        w = csv.writer(f, delimiter=";", lineterminator="\n")
        w.writerow(POS_HEADER)
        writer[teil] = w
    teil_je_jahr = {j: t for t, jahre in SPLITS.items() for j in jahre}

    zeilen_id, kauf_nr, zeilen, umsatz = 0, 0, 0, 0
    for tag in tage:
        lam = (BASIS_EINKAEUFE_PRO_TAG * fil["groesse"] * JAHRESFAKTOR[tag.year]
               * SAISON_FREQUENZ[tag.month - 1] * WOCHENTAG[tag.weekday()])
        n = round(lam * rnd.uniform(0.8, 1.2))   # Anzahl Einkäufe: Erwartungswert ±20 %
        zeitpunkte = sorted(
            datetime(tag.year, tag.month, tag.day, h, rnd.randrange(60), rnd.randrange(60))
            for h in rnd.choices(STUNDEN, STUNDEN_GEWICHT, k=n))
        kum = gewichte[tag.year]
        w = writer[teil_je_jahr[tag.year]]
        for zp in zeitpunkte:
            kauf_nr += 1
            referenz = f"{fil['code']}-{kauf_nr:07d}"
            kasse = rnd.choice(kassen)
            ma = rnd.choice(fil["mitarbeiter"])
            k = rnd.choices(POSITIONEN, POSITIONEN_GEWICHT)[0]
            gewaehlt, skus = [], set()
            while len(gewaehlt) < k:   # jeder Artikel nur einmal pro Einkauf
                a = rnd.choices(artikel, cum_weights=kum)[0]
                if a["sku"] not in skus:
                    skus.add(a["sku"])
                    gewaehlt.append(a)
            datum = zp.strftime("%Y-%m-%d %H:%M:%S")
            for a in gewaehlt:
                zeilen_id += 1
                mng = menge(rnd)
                final = mng * a["preis"]
                netto = round(final * 100 / (100 + a["steuer"]))
                steuer_name = "MwSt ermäßigt" if a["steuer"] == 7 else "MwSt voll"
                w.writerow([zeilen_id, referenz, datum, fil["code"], "prod", kasse, ma, "SALE", mng,
                            a["sku"], cent(a["preis"]), cent(final), a["name"], wg_namen[a["wg"]],
                            steuer_name, a["steuer"], cent(netto), cent(final - netto)])
                zeilen += 1
                umsatz += final
    for f in dateien.values():
        f.close()
    return fil["code"], kauf_nr, zeilen, umsatz


def schreibe_stammdaten(filialen, artikel):
    for teil in SPLITS:
        (OUT / teil).mkdir(parents=True, exist_ok=True)
        with open(OUT / teil / "filialen.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";", lineterminator="\n")
            w.writerow(["filiale_id", "filiale", "bundesland_nr", "bundesland", "ort"])
            for fil in filialen:
                w.writerow([fil["code"], fil["name"], f"{fil['bl']:02d}", fil["land"], fil["ort"]])
        with open(OUT / teil / "artikel.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";", lineterminator="\n")
            w.writerow(["artikelnummer", "artikelname", "stueckpreis", "warengruppe_nr", "warengruppe",
                        "steuer_rate"])
            for a in artikel:
                w.writerow([a["sku"], a["name"], cent(a["preis"]), a["wg"], WARENGRUPPEN[a["wg"]][0],
                            a["steuer"]])


def main():
    artikel = baue_artikel()
    filialen = baue_filialen()
    schreibe_stammdaten(filialen, artikel)
    tage = list(verkaufstage())
    auftraege = [(i, fil, artikel, tage) for i, fil in enumerate(filialen)]
    gesamt_kaeufe = gesamt_zeilen = gesamt_umsatz = 0
    with Pool() as pool:
        for code, kaeufe, zeilen, umsatz in pool.imap_unordered(generiere_filiale, auftraege):
            gesamt_kaeufe += kaeufe
            gesamt_zeilen += zeilen
            gesamt_umsatz += umsatz
            print(f"{code}: {kaeufe:>7} Einkäufe, {zeilen:>8} Positionen, {cent(umsatz):>14} EUR", flush=True)
    print(f"\nFilialen: {len(filialen)}, Artikel: {len(artikel)}, Verkaufstage: {len(tage)}")
    print(f"Einkäufe: {gesamt_kaeufe}, Positionen: {gesamt_zeilen}, Umsatz brutto: {cent(gesamt_umsatz)} EUR")


if __name__ == "__main__":
    main()
