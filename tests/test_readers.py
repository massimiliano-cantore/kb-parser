"""Tests for the format readers and the reader registry."""

from pathlib import Path

import pytest

from kb_parser.exceptions import (
    CorruptedContentError,
    DocumentReadError,
    EmptyDocumentError,
    UnsupportedFormatError,
)
from kb_parser.readers import (
    BaseReader,
    CsvReader,
    MarkdownReader,
    TxtReader,
    get_reader,
    register_reader,
)
from kb_parser.readers.base import EXCERPT_LENGTH, _find_date, _make_excerpt


def write(path: Path, content: str | bytes, encoding: str = "utf-8") -> Path:
    """Write a test file and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        content = content.encode(encoding)
    path.write_bytes(content)
    return path


# --- registry -------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "reader_class"),
    [("a.txt", TxtReader), ("a.MD", MarkdownReader), ("a.markdown", MarkdownReader),
     ("a.CSV", CsvReader)],
)
def test_get_reader_by_extension(name: str, reader_class: type) -> None:
    assert isinstance(get_reader(Path(name)), reader_class)


@pytest.mark.parametrize("name", ["report.pdf", "README", "archive.tar.gz"])
def test_unsupported_extension(name: str) -> None:
    with pytest.raises(UnsupportedFormatError):
        get_reader(Path(name))


def test_duplicate_registration_is_rejected() -> None:
    class OtherTxtReader(BaseReader):
        extensions = (".txt",)

        def parse(self, text: str, path: Path) -> tuple[str | None, str]:
            return None, text

    with pytest.raises(ValueError, match="already handled"):
        register_reader(OtherTxtReader)


# --- shared logic (BaseReader) ---------------------------------------------


def test_txt_basic_fields(tmp_path: Path) -> None:
    path = write(tmp_path / "notes" / "verbale.txt",
                 "Verbale riunione qualità\n\nData: 12/03/2025\nPresenti: Rossi, Bianchi.\n")
    document = TxtReader().read(path, root=tmp_path)
    assert document.title == "Verbale riunione qualità"
    assert document.date == "2025-03-12"
    assert document.file_format == "txt"
    assert document.path == "notes/verbale.txt"
    assert document.word_count == len(document.content.split())


@pytest.mark.parametrize("content", ["", "   \n\t\n  "])
def test_empty_file(tmp_path: Path, content: str) -> None:
    path = write(tmp_path / "empty.txt", content)
    with pytest.raises(EmptyDocumentError):
        TxtReader().read(path)


def test_latin1_file_is_decoded(tmp_path: Path) -> None:
    path = write(tmp_path / "old.txt", "Perché la qualità è più alta", encoding="latin-1")
    assert "Perché la qualità è più alta" in TxtReader().read(path).content


def test_windows_1252_quotes_are_decoded(tmp_path: Path) -> None:
    path = write(tmp_path / "win.txt", "L’operatore disse “ok” — 10 €", encoding="cp1252")
    assert TxtReader().read(path).content == "L’operatore disse “ok” — 10 €"


def test_utf8_bom_is_removed(tmp_path: Path) -> None:
    path = write(tmp_path / "bom.txt", "﻿Titolo\ntesto")
    assert TxtReader().read(path).title == "Titolo"


def test_utf16_with_bom_is_decoded(tmp_path: Path) -> None:
    path = write(tmp_path / "unicode.txt", "Scheda tecnica pompa", encoding="utf-16")
    assert TxtReader().read(path).title == "Scheda tecnica pompa"


def test_binary_file_with_txt_extension(tmp_path: Path) -> None:
    path = write(tmp_path / "fake.txt", bytes(range(256)) * 10)
    with pytest.raises(CorruptedContentError):
        TxtReader().read(path)


def test_binary_without_null_bytes(tmp_path: Path) -> None:
    path = write(tmp_path / "noise.txt", bytes(range(1, 32)) * 50)
    with pytest.raises(CorruptedContentError):
        TxtReader().read(path)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(DocumentReadError):
        TxtReader().read(tmp_path / "missing.txt")


def test_folder_with_txt_name(tmp_path: Path) -> None:
    folder = tmp_path / "folder.txt"
    folder.mkdir()
    with pytest.raises(DocumentReadError):
        TxtReader().read(folder)


def test_whitespace_is_normalized(tmp_path: Path) -> None:
    path = write(tmp_path / "spaces.txt", "Titolo\r\n\r\n\r\n\r\nuno   due\t\ttre  \r\n")
    assert TxtReader().read(path).content == "Titolo\n\nuno due tre"


def test_long_title_is_shortened(tmp_path: Path) -> None:
    path = write(tmp_path / "long.txt", "parola " * 100)
    assert len(TxtReader().read(path).title) <= 121


def test_excerpt_is_cut_at_word_end() -> None:
    excerpt = _make_excerpt("manutenzione " * 50)
    assert len(excerpt) <= EXCERPT_LENGTH + 1
    assert excerpt.endswith("manutenzione…")


def test_short_excerpt_is_unchanged() -> None:
    assert _make_excerpt("Testo breve.\nSeconda riga.") == "Testo breve. Seconda riga."


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Riunione del 2025-03-12", "2025-03-12"),
        ("Riunione del 5/3/2025", "2025-03-05"),
        ("Data errata 31/02/2025, corretta 01/03/2025", "2025-03-01"),
        ("Codice 12345-67-89 senza date", None),
        ("Nessuna data qui", None),
    ],
)
def test_find_date(text: str, expected: str | None) -> None:
    assert _find_date(text) == expected


# --- Markdown -----------------------------------------------------------------


def test_markdown_title_and_cleanup(tmp_path: Path) -> None:
    text = (
        "# Procedura **cambio** filtro\n\n"
        "Vedi il [manuale](http://example.com) e `config.yaml`.\n\n"
        "- primo passo\n1. secondo passo\n> nota importante\n\n"
        "| Codice | Descrizione |\n|---|---|\n| A12 | Filtro aria |\n"
    )
    document = MarkdownReader().read(write(tmp_path / "proc.md", text))
    assert document.title == "Procedura cambio filtro"
    for symbol in ("#", "**", "](", "`", "|", "---"):
        assert symbol not in document.content
    assert "manuale" in document.content
    assert "A12 Filtro aria" in document.content


def test_markdown_without_title_uses_file_name(tmp_path: Path) -> None:
    path = write(tmp_path / "appunti_turno.md", "Solo testo, nessun titolo.\n\n## Sezione\n")
    assert MarkdownReader().read(path).title == "appunti_turno"


def test_markdown_front_matter_title(tmp_path: Path) -> None:
    text = "---\ntitle: \"Scheda pompa\"\nauthor: x\n---\n# Altro\nTesto"
    document = MarkdownReader().read(write(tmp_path / "fm.md", text))
    assert document.title == "Scheda pompa"
    assert "author" not in document.content


def test_markdown_comment_in_code_is_not_title(tmp_path: Path) -> None:
    text = "Introduzione\n\n```python\n# not a title\nprint(1)\n```\n\n# Vero titolo\n"
    assert MarkdownReader().read(write(tmp_path / "code.md", text)).title == "Vero titolo"


def test_markdown_keeps_snake_case_words(tmp_path: Path) -> None:
    text = "# T\nIl parametro max_pressure_bar e _enfasi_."
    content = MarkdownReader().read(write(tmp_path / "snake.md", text)).content
    assert "max_pressure_bar" in content
    assert "enfasi." in content


def test_markdown_with_only_symbols_is_empty(tmp_path: Path) -> None:
    with pytest.raises(EmptyDocumentError):
        MarkdownReader().read(write(tmp_path / "rules.md", "---\n***\n___\n"))


# --- CSV ----------------------------------------------------------------------


def test_csv_semicolon_rows_become_text(tmp_path: Path) -> None:
    text = "codice;descrizione;quantità\nA12;Filtro aria;4\nB07;Guarnizione;\n"
    document = CsvReader().read(write(tmp_path / "ricambi.csv", text))
    assert document.title == "ricambi"
    assert document.content == (
        "codice: A12; descrizione: Filtro aria; quantità: 4\n"
        "codice: B07; descrizione: Guarnizione"
    )


def test_csv_comma_with_quoted_fields(tmp_path: Path) -> None:
    text = 'id,note\n1,"Sostituito filtro, controllata pressione"\n'
    document = CsvReader().read(write(tmp_path / "interventi.csv", text))
    assert document.content == "id: 1; note: Sostituito filtro, controllata pressione"


def test_csv_single_column(tmp_path: Path) -> None:
    document = CsvReader().read(write(tmp_path / "lista.csv", "matricola\nM001\nM002\n"))
    assert document.content == "matricola: M001\nmatricola: M002"


def test_csv_wrong_field_count(tmp_path: Path) -> None:
    text = "codice;descrizione\nA12;Filtro;extra\n"
    with pytest.raises(CorruptedContentError, match="line 2"):
        CsvReader().read(write(tmp_path / "rotto.csv", text))


def test_csv_unclosed_quote(tmp_path: Path) -> None:
    text = 'codice,note\nA12,"nota senza chiusura\n'
    with pytest.raises(CorruptedContentError):
        CsvReader().read(write(tmp_path / "quote.csv", text))


def test_csv_header_only(tmp_path: Path) -> None:
    with pytest.raises(EmptyDocumentError):
        CsvReader().read(write(tmp_path / "solo_header.csv", "codice;descrizione\n"))


def test_csv_blank_lines_are_skipped(tmp_path: Path) -> None:
    text = "\ncodice;descrizione\n\nA12;Filtro\n;\n"
    document = CsvReader().read(write(tmp_path / "vuote.csv", text))
    assert document.content == "codice: A12; descrizione: Filtro"
