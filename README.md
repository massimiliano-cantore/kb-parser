# kb-parser

Parser di documenti e indice per una knowledge base, scritto in Python con la sola libreria standard.

Data una cartella di documenti in formati diversi, il programma:

1. legge tutti i file, anche nelle sottocartelle, riconoscendo il formato dall'estensione;
2. estrae da ognuno le stesse informazioni: titolo, data, numero di parole, estratto e contenuto normalizzato;
3. costruisce un indice in cui cercare per parola chiave, filtrare per formato e calcolare statistiche;
4. salva l'indice in un file JSON leggibile, che si ricarica senza rileggere i documenti;
5. segnala i file che non riesce a elaborare (vuoti, binari, corrotti, con estensione non gestita), li salta
   e alla fine stampa un riepilogo con i motivi.

Formati gestiti: `.txt`, `.md` / `.markdown`, `.csv`.

## Requisiti

- Python 3.10 o superiore
- Nessuna dipendenza esterna (`pytest` solo per i test)

## Installazione

```bash
git clone https://github.com/massimiliano-cantore/kb-parser.git
cd kb-parser

python -m venv .venv
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\activate           # Windows

pip install -e .
pip install -r requirements-dev.txt   # solo per eseguire i test
```

In Google Colab bastano:

```python
!git clone https://github.com/massimiliano-cantore/kb-parser.git
%cd kb-parser
!pip install -q -e .
```

## Utilizzo

Tutti i comandi si lanciano con `python -m kb_parser` (oppure `kb-parser`, dopo l'installazione).
Se `--index` non è indicato, si usa `index.json` nella cartella corrente.

| Comando | Cosa fa |
|---|---|
| `build CARTELLA [--output FILE]` | Legge l'archivio, stampa il riepilogo e salva l'indice |
| `list [--sort path\|title\|date\|words]` | Elenca i documenti |
| `search PAROLA` | Cerca nel titolo e nel contenuto, i risultati più rilevanti per primi |
| `filter FORMATO` | Elenca i documenti di un formato (`txt`, `md`, `csv`) |
| `stats [--top N]` | Statistiche: documenti per formato, i più lunghi, date, file scartati |
| `show PERCORSO` | Mostra la scheda completa di un documento |

Esempio con l'archivio di prova incluso nel repository:

```bash
python -m kb_parser build sample_archive --output index.json
python -m kb_parser list --sort date
python -m kb_parser search "manutenzione"
python -m kb_parser filter csv
python -m kb_parser stats --top 3
python -m kb_parser show note/idee_nuovi_corsi.txt
```

Il programma termina con codice `0` se tutto va bene e `1` in caso di errore (indice mancante,
cartella inesistente, JSON non valido). Gli errori sono messaggi leggibili, senza traceback.
I file scartati durante `build` non sono un errore: compaiono nel riepilogo.

## Come vengono letti i documenti

| | `.txt` | `.md` | `.csv` |
|---|---|---|---|
| **Titolo** | prima riga non vuota | `title:` nel front matter YAML, altrimenti primo `# Titolo` | nome del file |
| **Contenuto** | testo completo | testo senza la sintassi Markdown (simboli, link, tabelle) | una riga per record: `colonna: valore; colonna: valore` |

Per tutti i formati:

- **titolo di riserva**: il nome del file, se il documento non ne ha uno;
- **data**: la prima data valida nel testo, nei formati `AAAA-MM-GG` o `GG/MM/AAAA`, salvata come
  `AAAA-MM-GG`. Le date impossibili (es. `31/02/2025`) sono ignorate;
- **estratto**: circa 200 caratteri, tagliati a fine parola;
- **codifica**: UTF-8 (con o senza BOM), UTF-16 con BOM, Windows-1252 e Latin-1;
- **spazi**: spazi multipli e righe vuote ripetute sono compattati.

File e cartelle nascosti (il cui nome inizia con `.`) vengono ignorati.

## Gestione degli errori

Ogni problema ha la sua eccezione, derivata da `KBParserError`:

| Eccezione | Quando | Esempi |
|---|---|---|
| `UnsupportedFormatError` | estensione non gestita | `.pdf`, file senza estensione |
| `EmptyDocumentError` | nessun testo utile | file vuoto, solo spazi, CSV con sola intestazione |
| `DocumentReadError` | il file non si può leggere | permessi, file oltre 50 MB, cartella illeggibile |
| `CorruptedContentError` | contenuto non valido | file binario rinominato `.txt`, CSV con colonne disallineate |
| `InvalidArchiveError` | la cartella indicata non esiste | percorso sbagliato |
| `IndexFileError` | problema con il file indice | indice mancante, JSON non valido, scheda incompleta |

Durante la scansione un file problematico viene registrato nel riepilogo con il motivo, e la
lettura continua con gli altri. Si ferma tutto solo se la cartella dell'archivio non esiste.

## Formato dell'indice

```json
{
  "format_version": 1,
  "created_at": "2026-11-02T12:51:54",
  "source_folder": "sample_archive",
  "document_count": 14,
  "documents": [
    {
      "title": "Verbale del collegio docenti",
      "date": "2024-12-20",
      "word_count": 82,
      "excerpt": "Verbale del collegio docenti Data: 20/12/2024 Il collegio si riunisce…",
      "file_format": "txt",
      "path": "verbali/verbale_collegio_docenti_2024.txt",
      "content": "Verbale del collegio docenti\n\nData: 20/12/2024\n\n..."
    }
  ],
  "skipped": [
    {"path": "file_vuoto.txt", "reason": "empty file", "message": "the file is empty"}
  ]
}
```

I percorsi sono relativi alla cartella dell'archivio, così l'indice non dipende dal computer su cui è
stato creato. Il salvataggio passa da un file temporaneo: un'interruzione non lascia un indice a metà.

## Archivio di prova

`sample_archive/` contiene 18 file in sei cartelle: procedure, verbali, schede tecniche, note e alcuni
casi limite costruiti apposta.

| File | Caso |
|---|---|
| `verbali/verbale_collegio_docenti_2024.txt` | salvato in Latin-1 |
| `schede_tecniche/fornitori_windows.csv` | salvato in Windows-1252, con `€` e virgolette tipografiche |
| `note/caratteri_speciali.txt` | accenti, simboli, emoji, alfabeti non latini, spazi e tabulazioni |
| `note/appunti_riunione_fornitori.md` | Markdown senza titolo |
| `storico/storico_interventi_manutenzione.txt` | file molto lungo (circa 55.000 parole) |
| `file_vuoto.txt` | file vuoto → scartato |
| `backup_corrotto.txt` | dati binari con estensione `.txt` → scartato |
| `registro_presenze_rotto.csv` | righe con un numero di colonne sbagliato → scartato |
| `manuale_piattaforma.pdf` | estensione non gestita → scartato |
| `.bozza_nascosta.txt` | file nascosto → ignorato |

Risultato atteso: 14 documenti elaborati, 4 scartati.

## Struttura del progetto

```
src/kb_parser/
├── document.py          # Document: la scheda normalizzata (dataclass)
├── exceptions.py        # gerarchia delle eccezioni
├── readers/
│   ├── base.py          # BaseReader: passi comuni a tutti i formati
│   ├── txt_reader.py
│   ├── markdown_reader.py
│   ├── csv_reader.py
│   └── __init__.py      # registro estensione → lettore
├── scanner.py           # ArchiveScanner e ScanReport
├── index.py             # KnowledgeBaseIndex: ricerca, filtri, statistiche, JSON
└── cli.py               # interfaccia da riga di comando
```

`BaseReader.read()` esegue i passi comuni (lettura, decodifica, controlli, data, estratto); ogni lettore
implementa solo `parse()`, la parte specifica del formato.

### Aggiungere un formato

```python
from pathlib import Path

from kb_parser.readers import BaseReader, register_reader


class LogReader(BaseReader):
    """Reads .log files."""

    extensions = (".log",)

    def parse(self, text: str, path: Path) -> tuple[str | None, str]:
        return None, text


register_reader(LogReader)
```

Il resto del programma (scanner, indice, CLI) non cambia.

## Test

```bash
pytest
```

I test coprono i lettori, i casi limite di codifica e formato, lo scanner, l'indice (ricerca, filtri,
statistiche, salvataggio e caricamento di file JSON non validi) e la riga di comando.
