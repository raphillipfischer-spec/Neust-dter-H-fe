#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Sequence, Tuple
from xml.sax.saxutils import escape

DateValue = Tuple[datetime, float]


@dataclass
class ConsumerResult:
    name: str
    series: List[DateValue]


def parse_dt(value: str) -> datetime:
    value = value.strip().replace("T", " ")
    fmts = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M"]
    for fmt in fmts:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise ValueError(f"Unbekanntes Datumsformat: {value}")


def read_csv_timeseries(path: Path, time_col: str, value_col: str) -> List[DateValue]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or time_col not in reader.fieldnames or value_col not in reader.fieldnames:
            raise ValueError(f"Spalten fehlen in {path}. Erwartet: {time_col}, {value_col}")
        out: List[DateValue] = []
        for row in reader:
            out.append((parse_dt(row[time_col]), float(row[value_col])))
    out.sort(key=lambda x: x[0])
    return out


def floor_to_interval(dt: datetime, minutes: int) -> datetime:
    discard = timedelta(minutes=dt.minute % minutes, seconds=dt.second, microseconds=dt.microsecond)
    return dt - discard


def resample(series: List[DateValue], target_minutes: int, method: str) -> List[DateValue]:
    if not series:
        return []
    method = method.lower()

    if method in {"mean", "sum"}:
        buckets: Dict[datetime, List[float]] = {}
        for dt, val in series:
            k = floor_to_interval(dt, target_minutes)
            buckets.setdefault(k, []).append(val)
        out: List[DateValue] = []
        for k in sorted(buckets.keys()):
            vals = buckets[k]
            out.append((k, sum(vals) if method == "sum" else (sum(vals) / len(vals))))
        return out

    if method == "interpolate":
        start = floor_to_interval(series[0][0], target_minutes)
        end = floor_to_interval(series[-1][0], target_minutes)
        src_t = [x[0] for x in series]
        src_v = [x[1] for x in series]

        def interp(target: datetime) -> float:
            if target <= src_t[0]:
                return src_v[0]
            if target >= src_t[-1]:
                return src_v[-1]
            for i in range(1, len(src_t)):
                if src_t[i] >= target:
                    t0, t1 = src_t[i - 1], src_t[i]
                    v0, v1 = src_v[i - 1], src_v[i]
                    span = (t1 - t0).total_seconds()
                    if span == 0:
                        return v1
                    ratio = (target - t0).total_seconds() / span
                    return v0 + (v1 - v0) * ratio
            return src_v[-1]

        out: List[DateValue] = []
        t = start
        while t <= end:
            out.append((t, interp(t)))
            t += timedelta(minutes=target_minutes)
        return out

    raise ValueError("Unbekannte Methode. Erlaubt: mean, sum, interpolate")


def adjust_percent(series: List[DateValue], percent: float) -> List[DateValue]:
    f = 1 + percent / 100.0
    return [(dt, val * f) for dt, val in series]


def to_map(series: List[DateValue]) -> Dict[datetime, float]:
    return {dt: val for dt, val in series}


def align_series(series: List[DateValue], target_index: Sequence[datetime]) -> List[DateValue]:
    src = to_map(series)
    if not src:
        return [(t, 0.0) for t in target_index]
    known = sorted(src.keys())
    out: List[DateValue] = []
    for t in target_index:
        if t in src:
            out.append((t, src[t]))
            continue
        prev = max((k for k in known if k < t), default=known[0])
        nxt = min((k for k in known if k > t), default=known[-1])
        if prev == nxt:
            out.append((t, src[prev]))
            continue
        r = (t - prev).total_seconds() / (nxt - prev).total_seconds()
        out.append((t, src[prev] + (src[nxt] - src[prev]) * r))
    return out


def load_scenario(path: Path) -> Dict:
    if path.suffix.lower() != ".json":
        raise ValueError("Aktuell wird nur JSON für --scenario unterstützt.")
    return json.loads(path.read_text(encoding="utf-8"))


def build_consumer(cfg: Dict, target_index: Sequence[datetime], target_minutes: int) -> ConsumerResult:
    ctype = cfg.get("type")
    name = cfg.get("name", ctype or "consumer")

    if ctype == "heat_pump_simple":
        base = float(cfg.get("base_kw", 2.5))
        day_factor = float(cfg.get("day_factor", 1.2))
        night_factor = float(cfg.get("night_factor", 0.8))
        start_h = int(cfg.get("day_start_hour", 6))
        end_h = int(cfg.get("day_end_hour", 22))
        weekend_factor = float(cfg.get("weekend_factor", 1.0))
        vals: List[DateValue] = []
        for t in target_index:
            v = base * (day_factor if start_h <= t.hour < end_h else night_factor)
            if t.weekday() >= 5:
                v *= weekend_factor
            vals.append((t, v))
        return ConsumerResult(name=name, series=vals)

    if ctype == "profile_file":
        s = read_csv_timeseries(Path(cfg["path"]), cfg.get("time_col", "timestamp"), cfg.get("value_col", "load_kw"))
        s = resample(s, target_minutes, cfg.get("resample_method", "mean"))
        s = align_series(s, target_index)
        scale = float(cfg.get("scale", 1.0))
        return ConsumerResult(name=name, series=[(t, v * scale) for t, v in s])

    raise ValueError(f"Unbekannter Verbrauchertyp: {ctype}")


def excel_serial(dt: datetime) -> float:
    epoch = datetime(1899, 12, 30)
    return (dt - epoch).total_seconds() / 86400.0


def sheet_xml(headers: List[str], rows: List[List[object]]) -> str:
    r = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
         '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']

    all_rows = [headers] + rows
    for i, row in enumerate(all_rows, start=1):
        r.append(f'<row r="{i}">')
        for j, cell in enumerate(row, start=1):
            col = ""
            n = j
            while n:
                n, rem = divmod(n - 1, 26)
                col = chr(65 + rem) + col
            ref = f"{col}{i}"
            if isinstance(cell, (int, float)) and not isinstance(cell, bool):
                if isinstance(cell, float) and (math.isnan(cell) or math.isinf(cell)):
                    cell = 0.0
                r.append(f'<c r="{ref}"><v>{cell}</v></c>')
            else:
                r.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(cell))}</t></is></c>')
        r.append("</row>")
    r.append("</sheetData></worksheet>")
    return "".join(r)


def write_xlsx(path: Path, sheets: List[Tuple[str, List[str], List[List[object]]]]) -> None:
    content_types = ['<?xml version="1.0" encoding="UTF-8"?>',
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
                     '<Default Extension="xml" ContentType="application/xml"/>',
                     '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>']
    for i in range(1, len(sheets) + 1):
        content_types.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
    content_types.append('</Types>')

    wb_sheets = []
    wb_rels = ['<?xml version="1.0" encoding="UTF-8"?>', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    for i, (name, _, _) in enumerate(sheets, start=1):
        safe = escape(name[:31])
        wb_sheets.append(f'<sheet name="{safe}" sheetId="{i}" r:id="rId{i}"/>')
        wb_rels.append(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>')
    wb_rels.append('</Relationships>')

    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets>{"".join(wb_sheets)}</sheets></workbook>'
    )

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "".join(content_types))
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", "".join(wb_rels))
        for i, (_, headers, rows) in enumerate(sheets, start=1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", sheet_xml(headers, rows))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Lastgänge anpassen und als Excel ausgeben")
    p.add_argument("--input", required=True, help="CSV-Eingabe")
    p.add_argument("--output", required=True, help="XLSX-Ausgabe")
    p.add_argument("--time-col", default="timestamp")
    p.add_argument("--value-col", default="load_kw")
    p.add_argument("--target-freq", default="15min")
    p.add_argument("--resample-method", default="mean", choices=["mean", "sum", "interpolate"])
    p.add_argument("--increase-percent", type=float, default=0.0)
    p.add_argument("--scenario", default=None, help="Optionale JSON-Szenario-Datei")
    return p.parse_args()


def freq_to_minutes(freq: str) -> int:
    f = freq.strip().lower()
    if not f.endswith("min"):
        raise ValueError("Nur Frequenzen im Format '<zahl>min' unterstützt, z. B. 15min")
    return int(f[:-3])


def main() -> None:
    args = parse_args()
    target_minutes = freq_to_minutes(args.target_freq)

    base = read_csv_timeseries(Path(args.input), args.time_col, args.value_col)
    base_rs = resample(base, target_minutes, args.resample_method)
    base_adj = adjust_percent(base_rs, args.increase_percent)

    target_idx = [t for t, _ in base_adj]
    consumers: List[ConsumerResult] = []
    if args.scenario:
        sc = load_scenario(Path(args.scenario))
        for c in sc.get("consumers", []):
            consumers.append(build_consumer(c, target_idx, target_minutes))

    total_map = {t: v for t, v in base_adj}
    for c in consumers:
        for t, v in c.series:
            total_map[t] = total_map.get(t, 0.0) + v
    total = sorted(total_map.items(), key=lambda x: x[0])

    sheets: List[Tuple[str, List[str], List[List[object]]]] = []
    sheets.append(("base_adjusted", ["timestamp", "base_adjusted_kw"], [[t.strftime("%Y-%m-%d %H:%M:%S"), v] for t, v in base_adj]))
    for c in consumers:
        sheets.append((f"consumer_{c.name}", ["timestamp", f"{c.name}_kw"], [[t.strftime("%Y-%m-%d %H:%M:%S"), v] for t, v in c.series]))
    sheets.append(("total", ["timestamp", "total_kw"], [[t.strftime("%Y-%m-%d %H:%M:%S"), v] for t, v in total]))

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_xlsx(out, sheets)
    print(f"OK: Datei geschrieben -> {out}")


if __name__ == "__main__":
    main()
