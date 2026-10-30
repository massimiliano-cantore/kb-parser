# kb-parser — Istruzioni per Claude Code

## Contesto

Progetto d'esame del Master ProfessionAI, corso "Programmazione con Python".
Cliente fittizio: Helix Formazione (referente: Responsabile Knowledge Management).

Obiettivo: un programma Python che, data una cartella di documenti in formati diversi,
ne estrae contenuto e metadati, li normalizza in una rappresentazione comune e
costruisce un indice della knowledge base, salvabile e ricaricabile da JSON.

**Criterio chiave di valutazione:** il parser deve reggere su un archivio che NON abbiamo
preparato noi. Robustezza e gestione degli errori contano più delle funzioni extra.

## Modalità di lavoro (IMPORTANTE)

- Lo sviluppatore scrive personalmente questi file:
  `src/kb_parser/document.py`, `src/kb_parser/exceptions.py`, `src/kb_parser/readers/base.py`.
  Non implementarli a meno che non venga chiesto esplicitamente. Puoi rileggerli,
  segnalare problemi e proporre miglioramenti spiegandone il motivo.
- Gli altri moduli (lettori concreti, scanner, indice, CLI, test, archivio di prova)
  possono essere sviluppati con Claude Code, seguendo il modello definito nei file sopra.
- Prima di una modifica non banale, descrivi il piano e attendi conferma.
- Spiega sempre le scelte progettuali: lo sviluppatore deve poter difendere ogni riga del codice.
- Quando ti viene chiesta una revisione, cerca soprattutto i modi in cui il codice si rompe
  con file imprevisti.

## Requisiti funzionali

1. Gestire almeno tre formati testuali: `.txt`, `.md`, `.csv`, riconoscendo il tipo di file e
   applicando la logica di lettura appropriata.
2. Da ogni documento estrarre un insieme comune di informazioni: titolo, data (se presente),
   numero di parole, breve estratto e contenuto normalizzato. Tutti i documenti hanno la
   stessa struttura, indipendentemente dal formato di origine.
3. Indice della knowledge base che permetta di:
   - elencare i documenti;
   - cercare per parola chiave nel titolo o nel contenuto;
   - filtrare per formato;
   - produrre statistiche di sintesi (documenti per tipo, i più lunghi, ecc.).
4. Salvare l'indice su file JSON e ricaricarlo senza rifare il parsing.
   Il JSON include il contenuto completo normalizzato di ogni documento.
5. Gestione degli errori centrale: file illeggibile, estensione non gestita o contenuto corrotto
   vengono segnalati con un messaggio chiaro e saltati, e il parsing prosegue sugli altri.
   Al termine, riepilogo di quanti documenti sono stati elaborati, quanti scartati e perché.

## Architettura

```
kb-parser/
├── pyproject.toml
├── requirements.txt          # dipendenze runtime (nessuna o quasi)
├── requirements-dev.txt      # pytest
├── README.md
├── CLAUDE.md
├── .gitignore
├── src/kb_parser/
│   ├── __init__.py
│   ├── __main__.py           # python -m kb_parser
│   ├── document.py           # Document (dataclass) con to_dict() / from_dict()
│   ├── exceptions.py         # gerarchia di eccezioni
│   ├── readers/
│   │   ├── __init__.py       # registro estensione → lettore, get_reader(path)
│   │   ├── base.py           # BaseReader (ABC, template method)
│   │   ├── txt_reader.py
│   │   ├── markdown_reader.py
│   │   └── csv_reader.py
│   ├── scanner.py            # ArchiveScanner + ScanReport
│   ├── index.py              # KnowledgeBaseIndex
│   └── cli.py                # argparse
├── sample_archive/           # archivio di prova (~15 documenti)
└── tests/
```

### Eccezioni

```
KBParserError                 # base comune
├── UnsupportedFormatError    # estensione non gestita
├── EmptyDocumentError        # file vuoto o solo spazi
├── DocumentReadError         # illeggibile (permessi, I/O, encoding)
└── CorruptedContentError     # contenuto malformato (es. CSV rotto, dati binari)
```

### BaseReader (template method)

`BaseReader.read(path)` esegue i passi comuni a tutti i formati:

1. legge il file grezzo, gestendo encoding ed errori di I/O;
2. se il file è vuoto, solleva `EmptyDocumentError`;
3. chiama `self.parse(raw_text)`, metodo astratto implementato dai lettori concreti,
   che restituisce titolo e contenuto normalizzato;
4. calcola `word_count` ed `excerpt` e cerca la data;
5. restituisce un `Document`.

I lettori concreti implementano solo `parse()` e dichiarano le estensioni gestite.
Aggiungere un formato = scrivere una classe nuova e registrarla, senza toccare il resto.

### Flusso

```
cartella → ArchiveScanner → registro → lettore giusto → Document
               ↓                                          ↓
          ScanReport (errori)                 KnowledgeBaseIndex ↔ index.json
                                                          ↑
                                                         CLI
```

### Comandi CLI previsti

```
python -m kb_parser build sample_archive --output index.json
python -m kb_parser list   --index index.json
python -m kb_parser search "manutenzione" --index index.json
python -m kb_parser filter csv --index index.json
python -m kb_parser stats  --index index.json
```

## Decisioni prese

1. **Titolo**: prima riga `# ...` nei `.md`; prima riga non vuota nei `.txt`;
   nome del file (senza estensione) come ultima risorsa.
2. **Data**: si cercano nel testo i formati `AAAA-MM-GG` e `GG/MM/AAAA`. Se assente, `None`
   (`null` nel JSON).
3. **Encoding**: prima UTF-8, poi Latin-1 come ripiego. Latin-1 decodifica qualsiasi sequenza
   di byte, quindi dopo la decodifica serve un controllo di plausibilità (byte nulli, alta
   percentuale di caratteri di controllo). Se il controllo fallisce, il file è considerato
   illeggibile o binario e viene scartato con un messaggio chiaro.
4. **Sottocartelle**: la scansione è ricorsiva.
5. **Ricerca**: per sottostringa (anche parti di parola), senza distinzione tra maiuscole e
   minuscole (usare `casefold()`), su titolo e contenuto.

## Punti ancora aperti

- Lunghezza dell'estratto (numero di caratteri o di parole).
- Trattamento di file e cartelle nascosti (es. `.DS_Store`, `.git`).
- Come trasformare le righe di un CSV in testo normalizzato.
- Cosa considerare "CSV malformato" (es. righe con numero di colonne diverso dall'intestazione).

## Convenzioni di codice

- Python 3.10 o superiore.
- Nomi di variabili, funzioni, classi e moduli in inglese; `snake_case`, `CamelCase` solo per le classi.
- Docstring in stile Google, in inglese, su moduli, classi e funzioni pubbliche
  (`Args:`, `Returns:`, `Raises:`).
- Type hints su tutte le funzioni.
- Nel pacchetto solo libreria standard: `pathlib`, `json`, `csv`, `argparse`, `dataclasses`,
  `abc`, `re`, `datetime`. `pytest` solo come dipendenza di sviluppo.
- Percorsi sempre con `pathlib.Path`, mai stringhe concatenate.
- Solo `cli.py` stampa a video: gli altri moduli restituiscono valori o sollevano eccezioni.
- Mai catturare eccezioni in modo generico e silenzioso. Ogni errore previsto ha la sua
  eccezione specifica e un messaggio comprensibile che include il nome del file.

## Comandi di sviluppo

```
python -m venv .venv
.venv\Scripts\activate         # Windows
pip install -e .
pip install -r requirements-dev.txt
pytest
```

## Consegna

- Formato richiesto: **link pubblico a un notebook Google Colab** (condiviso come
  "Chiunque abbia il link", ruolo "Visualizzatore").
- Il repository GitHub deve essere **pubblico** al momento della consegna (durante lo sviluppo
  resta privato).
- Il notebook di consegna clona il repo pubblico, installa il pacchetto e ne dimostra l'uso
  sull'archivio di prova: build dell'indice, riepilogo degli errori, elenco, ricerca, filtro,
  statistiche, salvataggio e ricaricamento del JSON. Deve funzionare su un runtime Colab nuovo,
  senza token né file locali.
- Il README deve contenere le istruzioni di installazione ed esecuzione.
- Lo sviluppo può avvenire in Colab: si clona il repo, si modificano i file `.py` e si fa push.

## Archivio di prova (`sample_archive/`)

Circa 15 documenti fittizi ma verosimili (procedure, verbali, schede tecniche, note) nei tre
formati, distribuiti anche in sottocartelle. Deve includere apposta casi difficili:

- file vuoto;
- file con caratteri accentati e speciali, e un file salvato in Latin-1;
- file con estensione non gestita;
- file molto lungo;
- CSV malformato;
- Markdown senza titolo;
- documenti con e senza data;
- file binario con estensione `.txt`.
