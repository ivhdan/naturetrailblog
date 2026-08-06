#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pubblica_blogger.py — riscrive il corpo dei post del blog con le schede generate.

Abbinamento: lo slug del post (ultima parte dell'URL, senza .html) deve
corrispondere al nome del file in schede/.
    https://naturetrailonblog.blogspot.com/2025/10/pian-fum.html
    → schede/pian-fum.html

PRIMA DI USARLO, DUE VOLTE:
  1. Blogger › Impostazioni › Gestisci blog › Esegui backup contenuti.
     Lo script sovrascrive il corpo dei post: senza backup non si torna indietro.
  2. Provalo con --limite 1 su una sola escursione.

Predefinito: modalità di prova, non scrive nulla. Serve --applica per pubblicare.

Preparazione (una volta sola):
    pip install google-api-python-client google-auth-oauthlib
    console.cloud.google.com → nuovo progetto → abilita "Blogger API v3"
    → Credenziali → ID client OAuth → tipo "Applicazione desktop"
    → scarica il JSON e salvalo qui come client_secret.json

Uso:
    python pubblica_blogger.py                      elenco e confronto, nessuna scrittura
    python pubblica_blogger.py --limite 1 --applica una sola scheda, per prova
    python pubblica_blogger.py --applica            tutte
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BLOG_ID = "6847632511964475641"          # Nature Trail Blog
SCOPI = ["https://www.googleapis.com/auth/blogger"]


def servizio(client_secret: Path, token: Path):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        sys.exit("Librerie mancanti. Esegui:\n"
                 "  pip install google-api-python-client google-auth-oauthlib")

    cred = None
    if token.exists():
        cred = Credentials.from_authorized_user_file(str(token), SCOPI)
    if not cred or not cred.valid:
        if cred and cred.expired and cred.refresh_token:
            cred.refresh(Request())
        else:
            if not client_secret.exists():
                sys.exit(f"Manca {client_secret}. Scaricalo da Google Cloud Console "
                         f"(Credenziali › ID client OAuth › Applicazione desktop).")
            cred = InstalledAppFlow.from_client_secrets_file(
                str(client_secret), SCOPI).run_local_server(port=0)
        token.write_text(cred.to_json(), encoding="utf-8")
    return build("blogger", "v3", credentials=cred)


def elenca_post(api) -> list[dict]:
    """Tutti i post, pubblicati e in bozza."""
    trovati, pagina = [], None
    while True:
        risposta = api.posts().list(
            blogId=BLOG_ID, maxResults=100, fetchBodies=False,
            status=["live", "draft"], pageToken=pagina).execute()
        trovati += risposta.get("items", [])
        pagina = risposta.get("nextPageToken")
        if not pagina:
            return trovati


def slug(post: dict) -> str:
    url = post.get("url") or ""
    return url.rstrip("/").split("/")[-1].replace(".html", "")


def mappa_slug(cartella_dati: Path) -> dict[str, str]:
    """slug del post → nome del file locale.

    Il nome del file segue la convenzione della rete (nodo__nodo), che Blogger
    non accetta negli indirizzi. Chi ha un indirizzo diverso lo dichiara nel
    proprio file dati con il campo "slug_blogger".
    """
    corrispondenze = {}
    for f in sorted(cartella_dati.glob("*.json")):
        try:
            dichiarato = json.loads(f.read_text(encoding="utf-8")).get("slug_blogger")
        except json.JSONDecodeError:
            dichiarato = None
        corrispondenze[dichiarato or f.stem] = f.stem
    return corrispondenze


def main() -> None:
    ap = argparse.ArgumentParser(description="Pubblica le schede sui post di Blogger.")
    ap.add_argument("--schede", type=Path, default=Path("schede"))
    ap.add_argument("--dati", type=Path, default=Path("dati"))
    ap.add_argument("--client-secret", type=Path, default=Path("client_secret.json"))
    ap.add_argument("--token", type=Path, default=Path("token.json"))
    ap.add_argument("--limite", type=int, help="ferma dopo N post")
    ap.add_argument("--slug", help="agisce su una sola escursione")
    ap.add_argument("--applica", action="store_true",
                    help="scrive davvero (senza questa opzione non tocca nulla)")
    args = ap.parse_args()

    api = servizio(args.client_secret, args.token)
    post = elenca_post(api)
    print(f"{len(post)} post trovati sul blog.\n")

    corrispondenze = mappa_slug(args.dati)

    da_fare, senza_scheda = [], []
    for p in post:
        s = slug(p)
        nome = corrispondenze.get(s, s)          # traduce lo slug nel nome locale
        if args.slug and args.slug not in (s, nome):
            continue
        f = args.schede / f"{nome}.html"
        (da_fare if f.exists() else senza_scheda).append((p, nome, f))

    if senza_scheda and not args.slug:
        print(f"{len(senza_scheda)} post senza scheda corrispondente "
              f"(manca schede/<slug>.html):")
        for _, s, _ in senza_scheda[:10]:
            print(f"   {s}")
        if len(senza_scheda) > 10:
            print(f"   … e altri {len(senza_scheda) - 10}")
        print()

    if args.limite:
        da_fare = da_fare[:args.limite]
    if not da_fare:
        sys.exit("Nessuna corrispondenza. Controlla che i nomi dei file in "
                 "schede/ coincidano con gli slug degli URL dei post.")

    if not args.applica:
        print("MODALITÀ DI PROVA — nessuna scrittura. Aggiungi --applica per pubblicare.\n")

    for p, s, f in da_fare:
        corpo = {"content": f.read_text(encoding="utf-8")}

        f_dati = args.dati / f"{s}.json"
        if f_dati.exists():
            etichette = json.loads(f_dati.read_text(encoding="utf-8")).get("etichette")
            if etichette:
                corpo["labels"] = etichette

        segno = "→" if args.applica else "·"
        print(f" {segno} {s:<38} {p.get('title', '')[:34]}")
        if args.applica:
            try:
                api.posts().patch(blogId=BLOG_ID, postId=p["id"], body=corpo).execute()
            except Exception as errore:
                print(f"   non aggiornato: {errore}", file=sys.stderr)

    print(f"\n{len(da_fare)} post {'aggiornati' if args.applica else 'pronti'}.")


if __name__ == "__main__":
    main()
