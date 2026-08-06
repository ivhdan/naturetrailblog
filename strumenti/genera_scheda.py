#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
genera_scheda.py — costruisce la scheda HTML dell'escursione per Blogger.

Legge tracce GPX e KML (anche gli export di Garmin Connect).

Uso:
    python genera_scheda.py traccia.kml dati.json
    python genera_scheda.py traccia.gpx dati.json -o scheda.html

Cosa fa:
  1. legge la traccia GPX o KML (solo libreria standard);
  1b. scarta i salti anomali: punti residui di attività precedenti,
      riavvii del GPS, tratti in auto;
  2. calcola lunghezza, D+, D-, quota min/max filtrando il rumore GPS;
  3. stima il tempo di percorrenza con la regola CAI/Scarf;
  4. disegna il profilo altimetrico come SVG inline (niente immagini da caricare);
  5. sostituisce i segnaposto {{...}} del template con i dati calcolati e con
     quelli scritti a mano nel file JSON.

I valori del JSON hanno la precedenza su quelli calcolati: se un rilievo va
corretto a mano, basta scriverlo nel JSON.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# ---------------------------------------------------------------- parametri
SOGLIA_DISLIVELLO_M = 4.0      # ignora oscillazioni minori: rumore barometrico
SOGLIA_SALTO_M = 500.0         # oltre questa distanza tra due punti la traccia si spezza
MIN_PUNTI_TRONCO = 20          # tronchi più corti sono frammenti da scartare
FINESTRA_MEDIA = 5             # campioni della media mobile sulle quote
VEL_ORIZZONTALE_KMH = 4.0      # velocità di riferimento su sentiero pianeggiante
VEL_SALITA_MH = 400.0          # metri di dislivello positivo all'ora
VEL_DISCESA_MH = 700.0         # metri di dislivello negativo all'ora
RAGGIO_TERRA_M = 6371000.0


# ------------------------------------------------------------- lettura tracce
Punto = tuple[float, float, float]      # (lat, lon, quota)


def _senza_ns(tag: str) -> str:
    return tag.split("}")[-1]


def leggi_gpx(percorso: Path) -> list[Punto]:
    radice = ET.parse(percorso).getroot()
    punti: list[Punto] = []
    for p in radice.iter():
        if _senza_ns(p.tag) != "trkpt":
            continue
        quota = 0.0
        for figlio in p:
            if _senza_ns(figlio.tag) == "ele" and figlio.text:
                quota = float(figlio.text)
        punti.append((float(p.get("lat")), float(p.get("lon")), quota))
    return punti


def leggi_kml(percorso: Path) -> list[Punto]:
    """Legge le LineString del KML. Ignora i Placemark puntuali, che negli
    export Garmin duplicano la geometria della linea."""
    radice = ET.fromstring(percorso.read_text(encoding="utf-8-sig"))
    punti: list[Punto] = []
    for elemento in radice.iter():
        if _senza_ns(elemento.tag) != "LineString":
            continue
        for figlio in elemento:
            if _senza_ns(figlio.tag) != "coordinates" or not figlio.text:
                continue
            for gettone in figlio.text.split():
                parti = gettone.split(",")
                punti.append((float(parti[1]), float(parti[0]),
                              float(parti[2]) if len(parti) > 2 else 0.0))
    return punti


def leggi_traccia(percorso: Path) -> list[Punto]:
    suffisso = percorso.suffix.lower()
    if suffisso == ".gpx":
        punti = leggi_gpx(percorso)
    elif suffisso == ".kml":
        punti = leggi_kml(percorso)
    else:
        raise ValueError(f"Formato non gestito: {suffisso}. Servono .gpx o .kml.")
    if not punti:
        raise ValueError("Nessun punto traccia trovato nel file.")
    return punti


def spezza(punti: list[Punto]) -> list[list[Punto]]:
    """Divide la traccia dove due punti consecutivi distano troppo."""
    tronchi: list[list[Punto]] = [[punti[0]]]
    for i in range(1, len(punti)):
        if distanza_m(punti[i - 1], punti[i]) > SOGLIA_SALTO_M:
            tronchi.append([])
        tronchi[-1].append(punti[i])
    return tronchi


def pulisci(punti: list[Punto]) -> tuple[list[Punto], list[str]]:
    """Tiene i tronchi consistenti, riporta quelli scartati."""
    tronchi = spezza(punti)
    tenuti, scartati = [], []
    for tronco in tronchi:
        if len(tronco) >= MIN_PUNTI_TRONCO:
            tenuti.append(tronco)
        else:
            scartati.append(f"{len(tronco)} punti presso "
                            f"{tronco[0][0]:.4f},{tronco[0][1]:.4f} "
                            f"(q. {tronco[0][2]:.0f} m)")
    if not tenuti:
        raise ValueError("Dopo la pulizia non resta nessun tratto utilizzabile.")
    uniti: list[Punto] = []
    for tronco in tenuti:
        uniti += tronco
    if len(tenuti) > 1:
        scartati.append(f"{len(tenuti)} tratti uniti in sequenza "
                        f"(andata/ritorno o interruzioni della registrazione)")
    return uniti, scartati


def distanza_m(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    """Distanza orizzontale (haversine).

    Volutamente planare e non 3D: è la convenzione di carte, cartelli e
    dispositivi GPS, quindi i chilometri della scheda sono confrontabili con
    quelli dell'orologio. Il dislivello è riportato a parte.
    """
    la1, lo1, _ = a
    la2, lo2, _ = b
    dlat = math.radians(la2 - la1)
    dlon = math.radians(lo2 - lo1)
    h = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(la1)) * math.cos(math.radians(la2)) * math.sin(dlon / 2) ** 2)
    return 2 * RAGGIO_TERRA_M * math.asin(math.sqrt(h))


def media_mobile(valori: list[float], n: int) -> list[float]:
    if n < 2 or len(valori) < n:
        return valori[:]
    fuori = []
    for i in range(len(valori)):
        i0 = max(0, i - n // 2)
        i1 = min(len(valori), i + n // 2 + 1)
        fuori.append(sum(valori[i0:i1]) / (i1 - i0))
    return fuori


def statistiche(punti: list[tuple[float, float, float]]) -> dict:
    quote = media_mobile([p[2] for p in punti], FINESTRA_MEDIA)

    distanze = [0.0]
    for i in range(1, len(punti)):
        distanze.append(distanze[-1] + distanza_m(punti[i - 1], punti[i]))

    dpos = dneg = 0.0
    riferimento = quote[0]
    for q in quote[1:]:
        delta = q - riferimento
        if abs(delta) >= SOGLIA_DISLIVELLO_M:      # isteresi sul dislivello
            if delta > 0:
                dpos += delta
            else:
                dneg -= delta
            riferimento = q

    km = distanze[-1] / 1000.0
    orizzontale = km / VEL_ORIZZONTALE_KMH
    verticale = dpos / VEL_SALITA_MH + dneg / VEL_DISCESA_MH
    ore = max(orizzontale, verticale) + 0.5 * min(orizzontale, verticale)

    forma, simbolo = sviluppo(punti)

    return {
        "punti": punti,
        "sviluppo": forma,
        "simbolo_sviluppo": simbolo,
        "quote": quote,
        "distanze_km": [d / 1000.0 for d in distanze],
        "lunghezza_km": round(km, 1),
        "dislivello_pos": int(round(dpos)),
        "dislivello_neg": int(round(dneg)),
        "quota_min": int(round(min(quote))),
        "quota_max": int(round(max(quote))),
        "ore_decimali": ore,
    }


CHIUSURA_M = 300.0        # sotto questa distanza partenza e arrivo coincidono
SOVRAPPOSIZIONE_M = 40.0  # due punti più vicini di così stanno sullo stesso sentiero
QUOTA_RICALCO = 0.50      # oltre questa frazione ricalcata è andata e ritorno


def sviluppo(punti: list[Punto]) -> tuple[str, str]:
    """Riconosce la forma del percorso: anello, andata e ritorno, traversata.

    Restituisce (etichetta, simbolo). Il criterio è geometrico: si guarda se
    partenza e arrivo coincidono e quanta parte del ritorno ricalca l'andata.
    """
    if distanza_m(punti[0], punti[-1]) > CHIUSURA_M:
        return "Lineare — traversata tra due punti diversi", "→"

    # il percorso si divide nel punto più lontano dalla partenza, che in un
    # andata e ritorno è l'inversione di marcia; dividere a metà dei punti
    # sbaglierebbe ogni volta che le due tratte hanno densità diverse
    lontananze = [distanza_m(punti[0], p) for p in punti]
    giro = lontananze.index(max(lontananze))
    andata, ritorno = punti[:giro], punti[giro:]
    if len(andata) < 10 or len(ritorno) < 10:
        return "Anello", "↻"

    # campionamento: il confronto punto a punto sarebbe inutilmente costoso
    campioni = andata[::max(1, len(andata) // 200)]
    confronto = ritorno[::max(1, len(ritorno) // 600)]
    ricalcati = sum(
        1 for a in campioni
        if any(distanza_m(a, b) < SOVRAPPOSIZIONE_M for b in confronto))

    if ricalcati / len(campioni) >= QUOTA_RICALCO:
        return "Andata e ritorno sullo stesso itinerario", "⇄"
    return "Anello", "↻"


def diagnosi_sviluppo(punti: list[Punto]) -> str:
    """Riga di controllo: quanto è stato ricalcato e quanto distano i capi."""
    lontananze = [distanza_m(punti[0], p) for p in punti]
    giro = lontananze.index(max(lontananze))
    andata, ritorno = punti[:giro], punti[giro:]
    if len(andata) < 10 or len(ritorno) < 10:
        return "traccia troppo corta per il confronto"
    campioni = andata[::max(1, len(andata) // 200)]
    confronto = ritorno[::max(1, len(ritorno) // 600)]
    ricalcati = sum(1 for a in campioni
                    if any(distanza_m(a, b) < SOVRAPPOSIZIONE_M for b in confronto))
    return (f"capi distanti {distanza_m(punti[0], punti[-1]):.0f} m, "
            f"ricalco {ricalcati / len(campioni):.0%}")


def ore_hm(ore: float) -> str:
    h = int(ore)
    m = int(round((ore - h) * 60))
    if m == 60:
        h, m = h + 1, 0
    return f"{h}:{m:02d}"


# ---------------------------------------------------------------- profilo SVG
FASCE_PENDENZA = [          # (soglia superiore, colore, etichetta)
    (0.15, "#47603f", "fino al 15%"),
    (0.25, "#8c6a47", "15–25%"),
    (9.99, "#b23a1b", "oltre il 25%"),
]
FINESTRA_PENDENZA_M = 25.0   # semiampiezza su cui misurare la pendenza


def _fascia(pendenza: float) -> int:
    for i, (soglia, _, _) in enumerate(FASCE_PENDENZA):
        if abs(pendenza) <= soglia:
            return i
    return len(FASCE_PENDENZA) - 1


def _pendenze(xs_km: list[float], ys: list[float]) -> list[int]:
    """Fascia di pendenza per ogni vertice.

    La pendenza si misura su una finestra di alcune decine di metri e non tra
    due punti consecutivi: sulla distanza breve il rumore del GPS produrrebbe
    un tratteggio di colori privo di significato.
    """
    fasce = []
    for i in range(len(xs_km)):
        j, k = i, i
        while j > 0 and (xs_km[i] - xs_km[j]) * 1000 < FINESTRA_PENDENZA_M:
            j -= 1
        while k < len(xs_km) - 1 and (xs_km[k] - xs_km[i]) * 1000 < FINESTRA_PENDENZA_M:
            k += 1
        base = (xs_km[k] - xs_km[j]) * 1000
        fasce.append(_fascia((ys[k] - ys[j]) / base) if base > 1 else 0)
    return fasce


def profilo_svg(st: dict, larghezza: int = 820, altezza: int = 230,
                passo_griglia_m: int = 200) -> str:
    """Profilo altimetrico in SVG inline, con la linea colorata per pendenza."""
    ml, mr, mt, mb = 46, 14, 16, 46
    w, h = larghezza - ml - mr, altezza - mt - mb

    xs, ys = st["distanze_km"], st["quote"]
    kmax = max(xs) or 1.0
    qmin = math.floor(min(ys) / passo_griglia_m) * passo_griglia_m
    qmax = math.ceil(max(ys) / passo_griglia_m) * passo_griglia_m
    span = (qmax - qmin) or 1

    fx = lambda k: ml + (k / kmax) * w
    fy = lambda q: mt + h - ((q - qmin) / span) * h

    passo = max(1, len(xs) // 900)
    idx = list(range(0, len(xs), passo))
    if idx[-1] != len(xs) - 1:
        idx.append(len(xs) - 1)
    cx = [xs[i] for i in idx]
    cy = [ys[i] for i in idx]
    fasce = _pendenze(cx, cy)
    punti = [(fx(a), fy(b)) for a, b in zip(cx, cy)]

    # area sottesa
    area = ("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in punti)
            + f" L{fx(kmax):.1f},{mt + h:.1f} L{ml:.1f},{mt + h:.1f} Z")

    # la linea si spezza in tratti omogenei per fascia di pendenza
    tratti, corrente, fascia_corrente = [], [punti[0]], fasce[0]
    for i in range(1, len(punti)):
        corrente.append(punti[i])
        if fasce[i] != fascia_corrente:
            tratti.append((fascia_corrente, corrente))
            corrente, fascia_corrente = [punti[i]], fasce[i]
    tratti.append((fascia_corrente, corrente))

    linee = "".join(
        f'<path d="M{" L".join(f"{x:.1f},{y:.1f}" for x, y in t)}" fill="none" '
        f'stroke="{FASCE_PENDENZA[f][1]}" stroke-width="2.2" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        for f, t in tratti if len(t) > 1)

    griglia, etichette = [], []
    q = qmin
    while q <= qmax:
        y = fy(q)
        griglia.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{ml + w}" y2="{y:.1f}"/>')
        etichette.append(f'<text x="{ml - 8}" y="{y + 3.5:.1f}" text-anchor="end">{int(q)}</text>')
        q += passo_griglia_m

    i_cima = cy.index(max(cy))
    cima_x, cima_y = punti[i_cima]
    cima_y_testo = cima_y - 8 if cima_y > mt + 16 else cima_y + 14

    passo_km = 1 if kmax <= 12 else (2 if kmax <= 30 else 5)
    k = 0
    while k <= kmax:
        etichette.append(
            f'<text x="{fx(k):.1f}" y="{mt + h + 15}" text-anchor="middle">{int(k)}</text>')
        k += passo_km

    legenda, lx = [], ml
    for _, colore, testo in FASCE_PENDENZA:
        legenda.append(
            f'<rect x="{lx}" y="{altezza - 15}" width="9" height="9" fill="{colore}" rx="1"/>'
            f'<text x="{lx + 13}" y="{altezza - 7}" font-size="8.5">{testo}</text>')
        lx += 96

    return f'''<svg viewBox="0 0 {larghezza} {altezza}" xmlns="http://www.w3.org/2000/svg"
     role="img" aria-label="Profilo altimetrico: {st['lunghezza_km']} km, {st['dislivello_pos']} metri di dislivello positivo, linea colorata per pendenza">
  <defs>
    <linearGradient id="sc-quote" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%"   stop-color="#8c6a47" stop-opacity=".45"/>
      <stop offset="45%"  stop-color="#5a7d5a" stop-opacity=".32"/>
      <stop offset="100%" stop-color="#47603f" stop-opacity=".10"/>
    </linearGradient>
  </defs>
  <g stroke="rgba(22,33,29,.14)" stroke-width="1">{''.join(griglia)}</g>
  <path d="{area}" fill="url(#sc-quote)"/>
  {linee}
  <circle cx="{cima_x:.1f}" cy="{cima_y:.1f}" r="3" fill="#b23a1b"/>
  <text x="{cima_x:.1f}" y="{cima_y_testo:.1f}" text-anchor="middle"
        font-family="IBM Plex Mono, monospace" font-size="9" fill="#b23a1b">{int(max(cy))}</text>
  <g font-family="IBM Plex Mono, monospace" font-size="9" fill="rgba(22,33,29,.55)">
    {''.join(etichette)}
    <text x="{ml}" y="{mt - 5}" font-size="8" letter-spacing="1.4">QUOTA m s.l.m.</text>
    <text x="{ml + w}" y="{mt + h + 15}" text-anchor="end" font-size="8" letter-spacing="1.4">KM</text>
    {''.join(legenda)}
  </g>
</svg>'''


# ---------------------------------------------------------------- composizione
SEGNAPOSTO = {
    "trattino": '<span class="sc-vuoto">—</span>',
    "todo": '<span style="opacity:.45;font-style:italic">da compilare</span>',
}


def _blocchi_condizionali(template: str, valori: dict) -> str:
    """Risolve i blocchi opzionali del template.

        <!--se:chiave-->   ... visibile solo se il campo è compilato ...   <!--/se:chiave-->
        <!--senza:chiave--> ... visibile solo se il campo è vuoto ...      <!--/senza:chiave-->

    Serve dove un segnaposto finisce dentro un attributo HTML (href, src):
    lì un riempitivo testuale romperebbe il markup, quindi è meglio non
    generare affatto l'elemento.
    """
    def compilato(chiave: str) -> bool:
        return valori.get(chiave) not in ("", None)

    template = re.sub(r"<!--se:(\w+)-->(.*?)<!--/se:\1-->",
                      lambda m: m.group(2) if compilato(m.group(1)) else "",
                      template, flags=re.S)
    return re.sub(r"<!--senza:(\w+)-->(.*?)<!--/senza:\1-->",
                  lambda m: "" if compilato(m.group(1)) else m.group(2),
                  template, flags=re.S)


def compila(template: str, valori: dict, vuoto: str = "trattino") -> tuple[str, list[str]]:
    """Sostituisce i {{segnaposto}}. Restituisce (html, elenco campi vuoti)."""
    template = _blocchi_condizionali(template, valori)
    riempitivo = SEGNAPOSTO.get(vuoto, vuoto)
    mancanti = set()

    def sostituisci(m):
        chiave = m.group(1)
        valore = valori.get(chiave, "")
        if valore == "" or valore is None:
            mancanti.add(chiave)
            return riempitivo
        return str(valore)

    return re.sub(r"\{\{(\w+)\}\}", sostituisci, template), sorted(mancanti)


def compatta(html: str) -> str:
    """Elimina gli a-capo del sorgente.

    L'editor di Blogger, se l'opzione delle interruzioni di riga è attiva,
    trasforma ogni a-capo del sorgente in un <br> e la scheda si riempie di
    spazi verticali. Con l'HTML su una riga sola il problema non si pone,
    qualunque sia l'impostazione del blog.
    """
    html = re.sub(r"\s*\n\s*", " ", html)
    return re.sub(r">\s+<", "><", html)


def costruisci(template: str, gpx: Path | None = None,
               dati: dict | None = None, vuoto: str = "trattino") -> tuple[str, list[str], dict]:
    """Compone una scheda. Senza GPX i campi calcolati restano vuoti.

    Restituisce (html, campi_mancanti, statistiche).
    st["note_pulizia"] elenca i tratti scartati o uniti.
    """
    calcolati, st, note = {}, {}, []
    if gpx is not None:
        punti, note = pulisci(leggi_traccia(gpx))
        st = statistiche(punti)
        calcolati = {
            "lunghezza_km": f"{st['lunghezza_km']:.1f}".replace(".", ","),
            "dislivello_pos": st["dislivello_pos"],
            "dislivello_neg": st["dislivello_neg"],
            "quota_min": st["quota_min"],
            "quota_max": st["quota_max"],
            "profilo_svg": profilo_svg(st),
            "gps_partenza": f"{st['punti'][0][0]:.5f}, {st['punti'][0][1]:.5f}",
            "gps_arrivo": f"{st['punti'][-1][0]:.5f}, {st['punti'][-1][1]:.5f}",
            "tipo_percorso": st["sviluppo"],
            "simbolo_sviluppo": st["simbolo_sviluppo"],
        }
    valori = {**calcolati, **(dati or {})}      # il JSON scritto a mano vince
    html, mancanti = compila(template, valori, vuoto)
    html = compatta(html)
    st["note_pulizia"] = note
    return html, mancanti, st


def main() -> None:
    ap = argparse.ArgumentParser(description="Compila la scheda escursione da GPX + JSON.")
    ap.add_argument("traccia", type=Path, help="file .gpx o .kml")
    ap.add_argument("dati", type=Path, help="JSON con i campi descrittivi")
    ap.add_argument("-t", "--template", type=Path,
                    default=Path("scheda-escursione-template.html"))
    ap.add_argument("-o", "--output", type=Path, default=Path("scheda.html"))
    ap.add_argument("--vuoto", default="trattino", choices=["trattino", "todo"],
                    help="come rendere i campi non compilati")
    args = ap.parse_args()

    dati = json.loads(args.dati.read_text(encoding="utf-8")) if args.dati.exists() else {}
    html, mancanti, st = costruisci(
        args.template.read_text(encoding="utf-8"), args.traccia, dati, args.vuoto)
    args.output.write_text(html, encoding="utf-8")

    print(f"{args.output}  ·  {st['lunghezza_km']} km  ·  D+ {st['dislivello_pos']} m  ·  "
          f"D− {st['dislivello_neg']} m  ·  quote {st['quota_min']}–{st['quota_max']} m")
    for nota in st["note_pulizia"]:
        print(f"  pulizia: {nota}", file=sys.stderr)
    if mancanti:
        print(f"{len(mancanti)} campi da compilare: " + ", ".join(mancanti), file=sys.stderr)


if __name__ == "__main__":
    main()
