# Lastgang-Szenario-Tool

Ein **einfaches, lokal lauffähiges Python-Tool ohne Adminrechte**, um Lastgänge für verschiedene Szenarien anzupassen und als Excel auszugeben.

## Funktionen
- Eingabe: CSV mit Zeitstempel + Lastwerten
- Resampling (z. B. 5-Minuten auf 15-Minuten)
- Prozentuale Anpassung der Basislast
- Zusatzverbraucher über Szenario-Datei (JSON), z. B. Wärmepumpe
- Ausgabe als Excel mit Sheets:
  - `base_adjusted`
  - `consumer_*`
  - `total`

## Voraussetzungen
- Python 3 (keine zusätzlichen Pakete nötig)

## Schnellstart (dein einfachstes Szenario)
Du hast 5-Minuten-Werte und willst auf 15-Minuten und danach z. B. +10 % erhöhen:

```bash
python3 load_tool.py \
  --input data/lastgang_5min.csv \
  --output out/lastgang_15min_plus10.xlsx \
  --time-col timestamp \
  --value-col load_kw \
  --target-freq 15min \
  --resample-method mean \
  --increase-percent 10
```

## Mit Zusatzverbrauchern (z. B. Wärmepumpe)
Beispiel-Szenario nutzen:

```bash
python3 load_tool.py \
  --input data/lastgang_5min.csv \
  --output out/mit_waermepumpe.xlsx \
  --target-freq 15min \
  --increase-percent 5 \
  --scenario scenario.example.json
```

## Format der Eingabedatei
Minimal:

| timestamp           | load_kw |
|--------------------|---------|
| 2026-01-01 00:00:00| 120.5   |
| 2026-01-01 00:05:00| 119.8   |

## Erweiterbarkeit
In der Szenario-Datei können mehrere Verbraucher definiert werden:
- `heat_pump_simple`: einfache, zeitabhängige Wärmepumpenlast
- `profile_file`: externer Lastgang aus CSV mit optionaler Skalierung

Damit kannst du später weitere Verbrauchertypen ergänzen.
