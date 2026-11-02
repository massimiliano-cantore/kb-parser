"""Tests for the command line interface."""

from pathlib import Path

import pytest

from kb_parser.cli import main

SAMPLE_ARCHIVE = Path(__file__).resolve().parent.parent / "sample_archive"


@pytest.fixture
def index_file(tmp_path: Path) -> Path:
    """Build the index of the sample archive and return its path."""
    path = tmp_path / "index.json"
    assert main(["build", str(SAMPLE_ARCHIVE), "--output", str(path)]) == 0
    return path


def test_build_prints_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "index.json"
    assert main(["build", str(SAMPLE_ARCHIVE), "--output", str(path)]) == 0
    output = capsys.readouterr().out
    assert "Processed:   14" in output
    assert "Skipped:     4" in output
    assert path.exists()


def test_list(index_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    assert main(["list", "--index", str(index_file), "--sort", "words"]) == 0
    output = capsys.readouterr().out
    assert output.startswith("14 documents")
    assert "storico/storico_interventi_manutenzione.txt" in output


def test_search(index_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    assert main(["search", "Laboratorio", "--index", str(index_file)]) == 0
    output = capsys.readouterr().out
    assert "contain 'Laboratorio'" in output
    assert "[laboratorio]" in output.lower()


def test_search_without_results(index_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    assert main(["search", "zzzz", "--index", str(index_file)]) == 0
    assert "No documents contain" in capsys.readouterr().out


def test_filter(index_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    assert main(["filter", "CSV", "--index", str(index_file)]) == 0
    assert "3 documents with format 'csv'" in capsys.readouterr().out


def test_stats(index_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    assert main(["stats", "--index", str(index_file), "--top", "2"]) == 0
    output = capsys.readouterr().out
    assert "Documents:        14" in output
    assert "Files skipped at build time: 4" in output


def test_show(index_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    assert main(["show", "note/idee_nuovi_corsi.txt", "--index", str(index_file)]) == 0
    assert "Title:   Idee per nuovi corsi" in capsys.readouterr().out


def test_show_missing_document(index_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["show", "nope.txt", "--index", str(index_file)]) == 1
    assert "no document with path" in capsys.readouterr().err


def test_missing_index_is_a_clean_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list", "--index", str(tmp_path / "none.json")]) == 1
    error = capsys.readouterr().err
    assert error.startswith("Error:")
    assert "Traceback" not in error


def test_missing_archive_is_a_clean_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["build", str(tmp_path / "missing")]) == 1
    assert "does not exist" in capsys.readouterr().err


def test_invalid_top(index_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["stats", "--index", str(index_file), "--top", "0"]) == 1


def test_missing_command() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main([])
    assert exit_info.value.code == 2
