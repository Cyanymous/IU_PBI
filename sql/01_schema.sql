-- Dimensionstabellen
CREATE TABLE dim_datum (
    datum_key		INTEGER PRIMARY KEY,
    datum		DATE    NOT NULL UNIQUE,
    datum_text		VARCHAR(10) NOT NULL,
    jahr		INTEGER NOT NULL,
    quartal		INTEGER NOT NULL,
    jahr_quartal	VARCHAR(7)  NOT NULL,
    monat_nr		INTEGER NOT NULL,
    monat_name		VARCHAR(10) NOT NULL,
    jahr_monat		VARCHAR(7)  NOT NULL,
    kw			INTEGER NOT NULL,
    tag_im_monat	INTEGER NOT NULL,
    tag_im_jahr		INTEGER NOT NULL,
    wochentag_nr	INTEGER NOT NULL,
    wochentag_name	VARCHAR(10) NOT NULL
);

CREATE TABLE dim_sku (
    artikelnummer_key	INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    artikelnummer	INTEGER NOT NULL UNIQUE,
    artikelname		VARCHAR(100) NOT NULL,
    stueckpreis		NUMERIC(10,2) NOT NULL,
    kategorie_nr	INTEGER NOT NULL,
    kategorie_name	VARCHAR(100) NOT NULL
);

CREATE TABLE dim_filiale (
    filiale_key		INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    filiale_id		INTEGER      NOT NULL UNIQUE,
    bundesland		VARCHAR(50)  NOT NULL,
    ort			VARCHAR(100) NOT NULL
);

--Faktentabelle
CREATE TABLE fakt_verkauf (
	artikelnummer_key 	INTEGER NOT NULL REFERENCES dim_sku(artikelnummer_key),
	filiale_key		INTEGER NOT NULL REFERENCES dim_filiale(filiale_key),
  	datum_key         	INTEGER NOT NULL REFERENCES dim_datum(datum_key),
	kauf_nr           	INTEGER NOT NULL,           -- Degenerate Dimension
	anzahl            	INTEGER NOT NULL CHECK (anzahl > 0),
	PRIMARY KEY (kauf_nr, artikelnummer_key)
);
