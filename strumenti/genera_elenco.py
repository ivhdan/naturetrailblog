#!/usr/bin/env python3
"""
genera_elenco.py — costruisce l'HTML della pagina "Elenco escursioni"
a partire da censimento_escursioni.csv

Uso:  python3 genera_elenco.py
Produce: elenco_escursioni.html  (da incollare in Blogger, vista HTML)

Gli articoli (tipo != "escursione") vengono esclusi dalla tabella.
"""
import csv
import html
import os
from collections import defaultdict

CSV = "censimento_escursioni.csv"
OUT = "elenco_escursioni.html"

MESI = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
        "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]

COLORE_DIFF = {
    "T":   "#3B6D11",
    "E":   "#854F0B",
    "EE":  "#A32D2D",
    "EEA": "#791F1F",
}


def colore(diff):
    return COLORE_DIFF.get(diff.strip().upper(), "#5F5E5A")


def data_estesa(iso):
    try:
        a, m, g = iso.split("-")
        return f"{int(g)} {MESI[int(m)]} {a}"
    except (ValueError, IndexError):
        return iso


def carica():
    with open(CSV, encoding="utf-8") as f:
        return [r for r in csv.DictReader(f, delimiter=";")]


def costruisci(righe):
    escursioni = [r for r in righe if r["tipo"] == "escursione"]
    escursioni.sort(key=lambda r: r["data_pubblicazione"], reverse=True)

    per_anno = defaultdict(list)
    for r in escursioni:
        per_anno[r["data_pubblicazione"][:4]].append(r)

    con_scheda = sum(1 for r in escursioni if r["traccia_gpx"].strip())

    p = []
    a = p.append

    a('<div style="font-family:Helvetica,Arial,sans-serif;max-width:900px;'
      'color:#2C2C2A;line-height:1.5">')

    a('<div style="border:1px solid #B4B2A9;padding:14px 16px;margin-bottom:22px;'
      'background:#F7F6F2">')
    a('<div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;'
      'color:#5F5E5A;margin-bottom:6px">Archivio dei rilievi</div>')
    a(f'<div style="font-size:14px">{len(escursioni)} escursioni censite '
      f'&mdash; {con_scheda} con scheda tecnica pubblicata.</div>')
    a('<div style="font-size:13px;color:#5F5E5A;margin-top:8px">'
      'Ogni voce corrisponde a un rilievo eseguito in una data precisa. '
      'Le condizioni descritte valgono per quella data: '
      'verificare lo stato attuale del percorso prima di partire.</div>')
    a('</div>')

    a('<input type="text" id="ntFiltro" placeholder="filtra per nome, area, sentiero..." '
      'style="width:100%;box-sizing:border-box;padding:8px 10px;margin-bottom:18px;'
      'border:1px solid #B4B2A9;font-size:14px;font-family:inherit">')

    for anno in sorted(per_anno, reverse=True):
        voci = per_anno[anno]
        a(f'<h3 style="font-size:15px;font-weight:600;margin:26px 0 8px;'
          f'padding-bottom:5px;border-bottom:2px solid #2C2C2A">'
          f'{anno} <span style="font-weight:400;color:#5F5E5A">'
          f'&middot; {len(voci)} rilievo</span></h3>' if len(voci) == 1 else
          f'&middot; {len(voci)} rilievi</span></h3>')

        a('<table style="width:100%;border-collapse:collapse;font-size:14px">')
        a('<tbody>')

        for r in voci:
            titolo = html.escape(r["titolo"])
            url = html.escape(r["url"])
            diff = r["difficolta"].strip()
            sent = r["sentiero"].strip()
            area = r["area"].strip()
            ha_scheda = bool(r["traccia_gpx"].strip())

            a('<tr class="ntRiga" style="border-bottom:1px solid #E1E0D9">')

            a('<td style="padding:9px 10px 9px 0;vertical-align:top;'
              'white-space:nowrap;color:#5F5E5A;font-size:13px;width:1%">'
              + data_estesa(r["data_pubblicazione"]) + '</td>')

            a('<td style="padding:9px 10px;vertical-align:top">')
            a(f'<a href="{url}" style="color:#185FA5;text-decoration:none;'
              f'font-weight:500">{titolo}</a>')
            dettagli = []
            if area:
                dettagli.append(html.escape(area))
            if sent:
                dettagli.append("sentiero " + html.escape(sent))
            if dettagli:
                a('<div style="font-size:12px;color:#5F5E5A;margin-top:2px">'
                  + " &middot; ".join(dettagli) + '</div>')
            a('</td>')

            a('<td style="padding:9px 10px;vertical-align:top;white-space:nowrap;'
              'text-align:right;width:1%">')
            if diff:
                a(f'<span style="display:inline-block;border:1px solid {colore(diff)};'
                  f'color:{colore(diff)};font-size:11px;font-weight:600;'
                  f'padding:1px 7px;letter-spacing:.04em">{html.escape(diff)}</span>')
            a('</td>')

            a('<td style="padding:9px 0 9px 10px;vertical-align:top;'
              'white-space:nowrap;text-align:right;width:1%;font-size:12px">')
            if ha_scheda:
                a('<span style="color:#0F6E56">scheda</span>')
            else:
                a('<span style="color:#B4B2A9">&mdash;</span>')
            a('</td>')

            a('</tr>')

        a('</tbody></table>')

    a('<p style="font-size:12px;color:#888780;margin-top:28px;'
      'border-top:1px solid #E1E0D9;padding-top:10px">'
      'Rilievi eseguiti con GPS. Elenco aggiornato progressivamente: '
      'le voci senza scheda tecnica sono in lavorazione.</p>')

    a('</div>')

    a('<script>')
    a('(function(){var i=document.getElementById("ntFiltro");if(!i)return;')
    a('i.addEventListener("input",function(){')
    a('var q=this.value.toLowerCase();')
    a('var righe=document.querySelectorAll(".ntRiga");')
    a('for(var n=0;n<righe.length;n++){')
    a('righe[n].style.display=righe[n].textContent.toLowerCase().indexOf(q)>-1?"":"none";}')
    a('});})();')
    a('</script>')

    return "\n".join(p)


def main():
    if not os.path.exists(CSV):
        print(f"Manca {CSV}")
        return 1
    righe = carica()
    testo = costruisci(righe)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(testo)
    n_esc = sum(1 for r in righe if r["tipo"] == "escursione")
    n_art = len(righe) - n_esc
    print(f"{OUT} scritto: {n_esc} escursioni in tabella, {n_art} articoli esclusi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
