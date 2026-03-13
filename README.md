# Lastgang-Szenario-Tool

Ein **einfaches, lokal lauffähiges Python-Tool ohne Adminrechte**, um **15-Minuten-Lastgänge** für verschiedene Szenarien anzupassen und als Excel auszugeben.

## Funktionen
- Eingabe: CSV mit Zeitstempel + Lastwerten (**nur 15-Minuten-Raster**) 
- Prozentuale Anpassung der Basislast
- Zusatzverbraucher über Szenario-Datei (JSON), z. B. Wärmepumpe
- Ausgabe als Excel mit Sheets:
  - `base_adjusted`
  - `consumer_*`
  - `total`

## Voraussetzungen
- Python 3 (keine zusätzlichen Pakete nötig)

## Schnellstart
Du hast 15-Minuten-Werte und willst z. B. +10 % erhöhen:

```bash
python3 load_tool.py \
  --input data/lastgang_15min.csv \
  --output out/lastgang_15min_plus10.xlsx \
  --time-col timestamp \
  --value-col load_kw \
  --increase-percent 10
```

## Mit Zusatzverbrauchern (z. B. Wärmepumpe)
Beispiel-Szenario nutzen:

```bash
python3 load_tool.py \
  --input data/lastgang_15min.csv \
  --output out/mit_waermepumpe.xlsx \
  --increase-percent 5 \
  --scenario scenario.example.json
```

## Hinweis zum Raster
Das Tool prüft den Basis-Lastgang auf exakte 15-Minuten-Abstände. Bei Abweichungen wird mit Fehlermeldung abgebrochen.

## Erweiterbarkeit
In der Szenario-Datei können mehrere Verbraucher definiert werden:
- `heat_pump_simple`: einfache, zeitabhängige Wärmepumpenlast
- `profile_file`: externer Lastgang aus CSV mit optionaler Skalierung (ebenfalls 15-Minuten-Raster)
