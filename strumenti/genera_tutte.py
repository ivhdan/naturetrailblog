#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
genera_tutte.py — costruisce in un colpo solo le schede di tutte le escursioni.

Struttura di lavoro attesa:

    naturetrail/
    ├── genera_scheda.py
    ├── genera_tutte.py
    ├── scheda-escursione-template.html
    ├── gpx/        pian-fum.gpx, val-di-genova.gpx, ...
    ├── dati/       pian-fum.json   (facoltativo, per i campi descrittivi)
    └── schede/     ← output

Il nome del file GPX deve coincidere con lo "slug" del post, cioè l'ultima
parte dell'URL senza estensione:
    .../2025/10/pian-fum.html   →   gpx/pian-fum.gpx

Uso:
    python genera_tutte.py                 tutte le tracce in gpx/
    python genera_tutte.py --vuoto todo    marca i campi da compilare
    python genera_tutte.py --slug pian-fum una sola escursione
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from genera_scheda import costruisci


def main() -> None:
    ap = argparse.ArgumentParser(description="Genera tutte le schede dalle tracce GPX.")
    ap.add_argument("--gpx", type=Path, default=Path("gpx"))
    ap.add_argument("--dati", type=Path, default=Path("dati"))
    ap.add_argument("--schede", type=Path, default=Path("schede"))
    ap.add_argument("--template", type=Path, default=Path("scheda-escursione-template.html"))
    ap.add_argument("--vuoto", default="trattino", choices=["trattino", "todo"])
    ap.add_argument("--slug", help="genera solo questa escursione")
    args = ap.parse_args()

    # gli script stanno in strumenti/, i dati nella radice del repository
    radice = Path(__file__).resolve().parent.parent
    import os
    os.chdir(radice)

    template = args.template.read_text(encoding="utf-8")
    args.schede.mkdir(exist_ok=True)

    tracce = sorted(list(args.gpx.glob("*.gpx")) + list(args.gpx.glob("*.kml")))
    if args.slug:
        tracce = [t for t in tracce if t.stem == args.slug]
    if not tracce:
        print(f"Nessuna traccia trovata in {args.gpx}/. "
              f"Copia lì i file .gpx, uno per escursione.", file=sys.stderr)
        sys.exit(1)

    print(f"{'escursione':<34} {'km':>6} {'D+':>6} {'D−':>6} {'quote':>12}  vuoti")
    print("─" * 78)

    totale_km = 0.0
    for traccia in tracce:
        slug = traccia.stem
        f_dati = args.dati / f"{slug}.json"
        dati = json.loads(f_dati.read_text(encoding="utf-8")) if f_dati.exists() else {}

        try:
            html, mancanti, st = costruisci(template, traccia, dati, args.vuoto)
        except Exception as errore:                       # traccia illeggibile
            print(f"{slug:<34} traccia non elaborabile: {errore}", file=sys.stderr)
            continue

        (args.schede / f"{slug}.html").write_text(html, encoding="utf-8")
        totale_km += st["lunghezza_km"]
        print(f"{slug:<34} {st['lunghezza_km']:>6.1f} {st['dislivello_pos']:>6d} "
              f"{st['dislivello_neg']:>6d} {st['quota_min']:>5d}–{st['quota_max']:<6d} "
              f"{len(mancanti):>3}")

    print("─" * 78)
    print(f"{len(tracce)} schede in {args.schede}/  ·  {totale_km:.0f} km complessivi")


if __name__ == "__main__":
    main()
