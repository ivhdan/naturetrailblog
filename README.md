# Nature Trail — archivio delle escursioni

Archivio delle tracce e generatore delle schede pubblicate su
[naturetrailonblog.blogspot.com](https://naturetrailonblog.blogspot.com/).

Questo repository è **la sorgente**: il blog ne è la stampa. Ogni scheda
pubblicata si può rigenerare da qui in qualsiasi momento.

---

## Struttura

```
gpx/       le tracce, una per tratta        pian-fum.kml
dati/      i campi descrittivi              pian-fum.json
schede/    l'HTML generato                  pian-fum.html   ← non modificare
strumenti/ gli script
scheda-escursione-template.html             la grafica, uguale per tutte
```

I nomi si corrispondono. `gpx/pian-fum.kml` + `dati/pian-fum.json`
producono `schede/pian-fum.html`, che finisce nel post il cui indirizzo
termina in `pian-fum.html`.

**Si lavora solo in `gpx/` e in `dati/`.** La cartella `schede/` viene
riscritta a ogni generazione: qualunque modifica fatta lì va persa.

---

## Dopo un'escursione

1. **Carica la traccia.** Apri la cartella `gpx/`, `Add file › Upload files`,
   trascina il KML. Rinominalo secondo la convenzione delle tratte:
   `nodo-partenza__nodo-arrivo.kml`.

2. **Crea il file dati.** Nella cartella `dati/`, `Add file › Create new file`.
   Nome uguale alla traccia ma con estensione `.json`. Copia il contenuto di un
   file esistente e cambia i valori.

3. **Salva** (`Commit changes`).

4. **Non fare altro.** La generazione parte da sola: nella scheda **Actions**
   vedi il pallino giallo che diventa verde. Dopo un minuto la scheda
   aggiornata è in `schede/`.

Se il pallino diventa rosso, aprilo: il messaggio dice quale file dati ha un
errore di sintassi e a quale riga.

---

## Regole dei file dati

Sono file JSON. Tre cose bastano a non sbagliare:

- ogni campo va tra virgolette, valore compreso: `"regione": "Piemonte"`
- virgola dopo ogni riga **tranne l'ultima**
- niente virgolette dentro i testi: usa gli apici `'`

I campi non presenti nel file compaiono nella scheda come *da compilare*.
Non è un errore: è il modo per pubblicare una scheda incompleta e completarla
nel tempo.

I campi ricavati dalla traccia — chilometri, dislivelli, quote, coordinate,
profilo altimetrico — **non vanno scritti**: si calcolano da soli. Se ne
scrivi uno a mano, il tuo valore ha la precedenza.

---

## Distinguere i dati verificati

Convenzione: i valori che non provengono dal rilievo diretto ma da fonti
esterne si scrivono preceduti da `DA VERIFICARE —`. Restano visibili in
scheda e ricordano cosa controllare alla prossima uscita.

---

## Generare in locale (facoltativo)

Non serve, ma se vuoi provare prima di pubblicare:

```
python strumenti/genera_tutte.py
python strumenti/genera_tutte.py --slug pian-fum
```

Nessuna libreria esterna: basta Python 3.10 o successivo.

---

## Pubblicare sul blog

```
python strumenti/pubblica_blogger.py --slug pian-fum --applica
```

Richiede le credenziali OAuth di Google, che **non stanno in questo
repository** (vedi `.gitignore`). In alternativa si incolla a mano il
contenuto del file da `schede/` nella vista HTML del post.

**Attenzione:** se usi la pubblicazione automatica, non modificare più le
schede dentro Blogger. Il senso di marcia è uno solo, da qui al blog.

---

## Storico

Ogni modifica a una traccia resta nella cronologia del repository, con data e
descrizione. È la tabella delle revisioni della scheda applicata alla
geometria del percorso: se un sentiero viene deviato da una frana e la traccia
cambia, la versione precedente resta consultabile.
