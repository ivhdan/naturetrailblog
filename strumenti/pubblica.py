#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pubblica.py — porta le schede generate sul blog, senza copia-incolla.

Pensato per girare dentro GitHub Actions, ma funziona anche da riga di comando.
Usa solo la libreria standard: nessun pacchetto da installare.

Credenziali attese come variabili d'ambiente (su GitHub: Settings › Secrets):
    BLOGGER_CLIENT_ID
    BLOGGER_CLIENT_SECRET
    BLOGGER_REFRESH_TOKEN

Comportamento:
  - per ogni scheda in schede/ cerca il post corrispondente sul blog;
  - se lo trova, ne riscrive il corpo;
  - se non lo trova, crea un post nuovo come BOZZA e scrive l'indirizzo
    assegnato da Blogger dentro il file dati, così il collegamento resta.

L'abbinamento usa il campo "slug_blogger" del file dati; in mancanza, il nome
del file. Senza --applica non scrive nulla.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BLOG_ID = "6847632511964475641"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = f"https://www.googleapis.com/blogger/v3/blogs/{BLOG_ID}/posts"


# ------------------------------------------------------------------ trasporto
def _chiamata(url: str, dati: bytes | None = None, intestazioni: dict | None = None,
              metodo: str | None = None) -> dict:
    richiesta = urllib.request.Request(url, data=dati, method=metodo,
                                       headers=intestazioni or {})
    try:
        with urllib.request.urlopen(richiesta, timeout=60) as risposta:
            corpo = risposta.read().decode("utf-8")
            return json.loads(corpo) if corpo else {}
    except urllib.error.HTTPError as errore:
        dettaglio = errore.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"HTTP {errore.code} su {url}\n{dettaglio}") from None


def accesso() -> str:
    """Scambia il refresh token con un token d'accesso valido un'ora."""
    mancanti = [n for n in ("BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET",
                            "BLOGGER_REFRESH_TOKEN") if not os.environ.get(n)]
    if mancanti:
        sys.exit("Credenziali assenti: " + ", ".join(mancanti)
                 + "\nVanno impostate in Settings › Secrets and variables › Actions.")

    corpo = urllib.parse.urlencode({
        "client_id": os.environ["BLOGGER_CLIENT_ID"],
        "client_secret": os.environ["BLOGGER_CLIENT_SECRET"],
        "refresh_token": os.environ["BLOGGER_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    risposta = _chiamata(TOKEN_URL, corpo,
                         {"Content-Type": "application/x-www-form-urlencoded"})
    return risposta["access_token"]


def _json(url: str, token: str, corpo: dict | None = None,
          metodo: str | None = None) -> dict:
    intestazioni = {"Authorization": f"Bearer {token}"}
    dati = None
    if corpo is not None:
        dati = json.dumps(corpo).encode("utf-8")
        intestazioni["Content-Type"] = "application/json"
    return _chiamata(url, dati, intestazioni, metodo)


# --------------------------------------------------------------------- blog
def elenco_post(token: str) -> dict[str, dict]:
    """Tutti i post del blog, indicizzati per slug."""
    trovati, pagina = {}, None
    while True:
        parametri = {"maxResults": "100", "fetchBodies": "false", "view": "ADMIN"}
        if pagina:
            parametri["pageToken"] = pagina
        risposta = _json(f"{API}?{urllib.parse.urlencode(parametri)}", token)
        for post in risposta.get("items", []):
            slug = (post.get("url") or "").rstrip("/").split("/")[-1].replace(".html", "")
            if slug:
                trovati[slug] = post
        pagina = risposta.get("nextPageToken")
        if not pagina:
            return trovati


def leggi_dati(percorso: Path) -> dict:
    try:
        return json.loads(percorso.read_text(encoding="utf-8")) if percorso.exists() else {}
    except json.JSONDecodeError:
        return {}


def registra_slug(percorso: Path, slug: str) -> None:
    """Scrive nel file dati l'indirizzo assegnato da Blogger."""
    dati = leggi_dati(percorso)
    dati["slug_blogger"] = slug
    percorso.write_text(json.dumps(dati, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")


# --------------------------------------------------------------------- flusso
def main() -> None:
    ap = argparse.ArgumentParser(description="Pubblica le schede sul blog.")
    ap.add_argument("--schede", type=Path, default=Path("schede"))
    ap.add_argument("--dati", type=Path, default=Path("dati"))
    ap.add_argument("--slug", help="agisce su una sola escursione")
    ap.add_argument("--applica", action="store_true",
                    help="scrive davvero; senza questa opzione elenca soltanto")
    args = ap.parse_args()

    radice = Path(__file__).resolve().parent.parent
    os.chdir(radice)

    schede = sorted(args.schede.glob("*.html"))
    if args.slug:
        schede = [s for s in schede if s.stem == args.slug]
    if not schede:
        sys.exit(f"Nessuna scheda in {args.schede}/.")

    token = accesso()
    post = elenco_post(token)
    print(f"{len(post)} post sul blog, {len(schede)} schede locali.\n")

    if not args.applica:
        print("PROVA — nessuna scrittura. Aggiungi --applica per pubblicare.\n")

    aggiornati = creati = invariati = 0
    for scheda in schede:
        f_dati = args.dati / f"{scheda.stem}.json"
        dati = leggi_dati(f_dati)
        slug = dati.get("slug_blogger") or scheda.stem
        html = scheda.read_text(encoding="utf-8")
        esistente = post.get(slug)

        if esistente:
            print(f"  aggiorna  {slug:<38} {esistente.get('title', '')[:32]}")
            if args.applica:
                _json(f"{API}/{esistente['id']}", token, {"content": html}, "PATCH")
                aggiornati += 1
        else:
            titolo = dati.get("titolo") or scheda.stem.replace("_", " ")
            print(f"  crea      {slug:<38} {titolo[:32]}  (bozza)")
            if args.applica:
                nuovo = _json(f"{API}/?isDraft=true", token,
                              {"title": titolo, "content": html})
                assegnato = (nuovo.get("url") or "").rstrip("/").split("/")[-1]
                assegnato = assegnato.replace(".html", "")
                if assegnato and f_dati.exists():
                    registra_slug(f_dati, assegnato)
                    print(f"            indirizzo assegnato: {assegnato}")
                creati += 1

    if args.applica:
        print(f"\n{aggiornati} aggiornati, {creati} creati come bozza.")
        if creati:
            print("Le bozze vanno pubblicate a mano dal pannello di Blogger: "
                  "è l'occasione per controllare titolo e indirizzo prima che "
                  "diventino definitivi.")
    else:
        print(f"\n{len(schede)} schede pronte.")


if __name__ == "__main__":
    main()
