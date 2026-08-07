#!/usr/bin/env python3
"""
audit_tracce.py — censimento delle tracce in gpx/

Legge ogni GPX/KML e riporta: strumento di registrazione (dal creator),
presenza e intervallo dei timestamp, numero di punti.
NON modifica alcun file. Serve a decidere prima di scrivere logica.

Uso:  python3 strumenti/audit_tracce.py [cartella]
"""
import glob
import os
import sys
import re
import xml.etree.ElementTree as ET


# --- mappatura creator -> strumento leggibile -------------------------------
# Confronto per sottostringa, case-insensitive. Il primo che corrisponde vince.
STRUMENTI = [
    # specifiche prima delle generiche: la prima corrispondenza vince
    ("etrex 32x",    "GPS Garmin eTrex 32x"),
    ("keymaze",      "GPS Geonaute Keymaze"),
    ("onmove",       "GPS Geonaute ONmove"),
    ("etrex",        "GPS Garmin eTrex (modello da precisare)"),
    ("geonaute",     "GPS Geonaute (modello da precisare)"),
    ("google earth", "tracciato ridisegnato (Google Earth)"),
    ("basecamp",     "esportato da Garmin BaseCamp"),
]


def identifica_strumento(creator):
    if not creator:
        return None
    c = creator.lower()
    for chiave, etichetta in STRUMENTI:
        if chiave in c:
            return etichetta
    return None


# I KML non hanno l'attributo 'creator': il software che esporta lascia pero'
# tracce nel corpo del file (URL delle icone di stile, commenti, tag propri).
FIRME = [
    ("software.geonaute.com", "GPS Geonaute (da export KML)"),
    ("www.garmin.com",        "Garmin (da export KML)"),
    ("earth.google.com",      "tracciato ridisegnato (Google Earth)"),
    ("strava.com",            "Strava (da export KML)"),
]


def identifica_da_firma(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            testo = f.read().lower()
    except OSError:
        return None
    for chiave, etichetta in FIRME:
        if chiave in testo:
            return etichetta
    return None


def _locale(tag):
    """Rimuove il namespace: '{http://...}trkpt' -> 'trkpt'."""
    return tag.rsplit("}", 1)[-1]


def analizza(path):
    ris = {
        "file": os.path.basename(path),
        "creator": None,
        "strumento": None,
        "n_tempi": 0,
        "primo": None,
        "ultimo": None,
        "punti": 0,
        "errore": None,
        "traversata": "__" in os.path.basename(path),
        "n_tempi_distinti": 0,
        "tempo_non_progressivo": False,
        "quote_distinte": 0,
        "senza_quote": False,
    }

    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as e:
        ris["errore"] = f"XML non valido: {e}"
        return ris

    ris["creator"] = root.get("creator")
    ris["strumento"] = identifica_strumento(ris["creator"])
    if not ris["strumento"]:
        ris["strumento"] = identifica_da_firma(path)

    tempi = []
    punti = 0
    quote = []

    for el in root.iter():
        nome = _locale(el.tag)

        if nome == "trkpt":
            punti += 1
            for figlio in el:
                if _locale(figlio.tag) == "ele" and figlio.text:
                    quote.append(float(figlio.text))
            # l'ora si legge SOLO dentro il punto traccia.
            # <time> in <metadata> e' l'ora di export, non del rilievo.
            for figlio in el:
                if _locale(figlio.tag) == "time" and figlio.text:
                    tempi.append(figlio.text.strip())

        elif nome == "coord":              # KML gx:Track
            punti += 1
            parti = (el.text or "").split()
            if len(parti) >= 3:
                quote.append(float(parti[2]))

        elif nome == "when" and el.text:   # KML gx:Track
            tempi.append(el.text.strip())

        elif nome == "coordinates" and el.text:
            # LineString KML: molti punti in un solo tag, nessun tempo
            for tok in el.text.split():
                punti += 1
                parti = tok.split(",")
                if len(parti) >= 3:
                    quote.append(float(parti[2]))

    tempi.sort()
    ris["n_tempi"] = len(tempi)
    ris["n_tempi_distinti"] = len(set(tempi))
    # un solo istante ripetuto su tutti i punti = marcatura unica dell'export,
    # non registrazione progressiva: niente andamento temporale, solo la data
    ris["tempo_non_progressivo"] = len(tempi) > 1 and len(set(tempi)) == 1
    ris["punti"] = punti
    ris["quote_distinte"] = len(set(quote))
    ris["senza_quote"] = len(quote) == 0 or len(set(quote)) == 1
    if tempi:
        ris["primo"] = tempi[0][:10]
        ris["ultimo"] = tempi[-1][:10]

    return ris


def main():
    cartella = sys.argv[1] if len(sys.argv) > 1 else "gpx"
    percorsi = sorted(
        glob.glob(os.path.join(cartella, "*.gpx"))
        + glob.glob(os.path.join(cartella, "*.kml"))
    )

    if not percorsi:
        print(f"Nessuna traccia trovata in '{cartella}/'")
        return 1

    righe = [analizza(p) for p in percorsi]

    print(f"{'file':<38} {'strumento':<34} {'data':<11} {'pt':>5}  tipo")
    print("-" * 100)
    for r in righe:
        if r["errore"]:
            print(f"{r['file']:<38} !! {r['errore'][:55]}")
            continue
        strum = r["strumento"] or f"?? creator: {r['creator'] or 'assente'}"
        data = r["primo"] or "SENZA TEMPO"
        tipo = "traversata" if r["traversata"] else ""
        print(f"{r['file']:<38} {strum[:33]:<34} {data:<11} {r['punti']:>5}  {tipo}")

    # --- riepilogo ---------------------------------------------------------
    errori = [r for r in righe if r["errore"]]
    senza_tempo = [r for r in righe if not r["errore"] and r["n_tempi"] == 0]
    ignoti = [r for r in righe if not r["errore"] and not r["strumento"]]
    multigiorno = [
        r for r in righe
        if r["primo"] and r["ultimo"] and r["primo"] != r["ultimo"]
    ]

    print(f"\n{len(righe)} tracce esaminate")

    if errori:
        print(f"\n  {len(errori)} NON LEGGIBILI — da correggere:")
        for r in errori:
            print(f"    · {r['file']}")

    if senza_tempo:
        print(f"\n  {len(senza_tempo)} senza timestamp — data da dichiarare a mano:")
        for r in senza_tempo:
            print(f"    · {r['file']}")

    if ignoti:
        print(f"\n  {len(ignoti)} con creator non mappato — da aggiungere a STRUMENTI:")
        for r in ignoti:
            print(f"    · {r['file']:<34} creator: {r['creator'] or 'assente'}")

    if multigiorno:
        print(f"\n  {len(multigiorno)} su piu' giorni — verificare se e' un trekking:")
        for r in multigiorno:
            print(f"    · {r['file']:<34} {r['primo']} -> {r['ultimo']}")

    senza_quote = [r for r in righe if not r["errore"] and r["senza_quote"]]
    if senza_quote:
        print(f"\n  {len(senza_quote)} SENZA ALTIMETRIA — dislivello non calcolabile:")
        for r in senza_quote:
            print(f"    · {r['file']:<34} quote distinte: {r['quote_distinte']}")

    non_progressive = [r for r in righe if r.get("tempo_non_progressivo")]
    if non_progressive:
        print(f"\n  {len(non_progressive)} con TEMPO NON PROGRESSIVO "
              f"(un solo istante su tutti i punti):")
        for r in non_progressive:
            print(f"    · {r['file']:<34} data utilizzabile: {r['primo']}")

    nomi_irregolari = [
        r for r in righe
        if re.search(r"[A-Z\s.àèéìòù]", os.path.splitext(r["file"])[0])
        or ("_" in os.path.splitext(r["file"])[0]
            and "__" not in os.path.splitext(r["file"])[0])
    ]
    if nomi_irregolari:
        print(f"\n  {len(nomi_irregolari)} nomi fuori convenzione:")
        for r in nomi_irregolari:
            print(f"    · {r['file']}")

    strumenti_usati = sorted({r["strumento"] for r in righe if r["strumento"]})
    if len(strumenti_usati) > 1:
        print(f"\n  ATTENZIONE: {len(strumenti_usati)} strumenti diversi in archivio.")
        for s in strumenti_usati:
            n = sum(1 for r in righe if r["strumento"] == s)
            print(f"    · {s} ({n})")
        print("    'strumentazione' non puo' stare in _comuni.json.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
