"""Tests for the archive scanner and the scan report."""

from pathlib import Path

import pytest

from kb_parser.exceptions import InvalidArchiveError
from kb_parser.scanner import ArchiveScanner


def write(path: Path, content: str | bytes) -> None:
    """Write a test file, creating parent folders."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        content = content.encode("utf-8")
    path.write_bytes(content)


@pytest.fixture
def archive(tmp_path: Path) -> Path:
    """Build a small archive with good and bad files."""
    write(tmp_path / "procedura.md", "# Procedura\nTesto della procedura.")
    write(tmp_path / "verbali" / "q1.txt", "Verbale Q1\nData 2025-01-15")
    write(tmp_path / "verbali" / "2025" / "q2.txt", "Verbale Q2\nTesto")
    write(tmp_path / "dati" / "ricambi.csv", "codice;qta\nA1;3\n")
    write(tmp_path / "vuoto.txt", "")
    write(tmp_path / "manuale.pdf", b"%PDF-1.4")
    write(tmp_path / "rotto.csv", "a;b\n1;2;3\n")
    write(tmp_path / "binario.txt", bytes(range(256)))
    write(tmp_path / ".DS_Store", b"\x00\x01")
    write(tmp_path / ".git" / "config.txt", "should be ignored")
    return tmp_path


def test_scan_processes_good_files_recursively(archive: Path) -> None:
    documents, report = ArchiveScanner(archive).scan()
    expected = {"procedura.md", "dati/ricambi.csv", "verbali/q1.txt", "verbali/2025/q2.txt"}
    assert {document.path for document in documents} == expected
    assert set(report.processed) == expected


def test_scan_reports_skipped_files_with_reasons(archive: Path) -> None:
    _, report = ArchiveScanner(archive).scan()
    assert report.processed_count == 4
    assert report.skipped_count == 4
    assert report.skipped_by_reason() == {
        "corrupted content": 2,
        "empty file": 1,
        "unsupported format": 1,
    }


def test_hidden_files_are_ignored(archive: Path) -> None:
    _, report = ArchiveScanner(archive).scan()
    every_path = report.processed + [item.path for item in report.skipped]
    assert not any(part.startswith(".") for path in every_path for part in path.split("/"))


def test_scan_is_deterministic(archive: Path) -> None:
    first, _ = ArchiveScanner(archive).scan()
    second, _ = ArchiveScanner(archive).scan()
    assert first == second


def test_summary_mentions_counts_and_files(archive: Path) -> None:
    _, report = ArchiveScanner(archive).scan()
    summary = report.summary()
    assert "Processed:   4" in summary
    assert "Skipped:     4" in summary
    assert "manuale.pdf" in summary
    assert "rotto.csv" in summary


def test_missing_archive(tmp_path: Path) -> None:
    with pytest.raises(InvalidArchiveError):
        ArchiveScanner(tmp_path / "missing").scan()


def test_archive_is_a_file(tmp_path: Path) -> None:
    file = tmp_path / "file.txt"
    file.write_text("x")
    with pytest.raises(InvalidArchiveError):
        ArchiveScanner(file).scan()


def test_empty_archive(tmp_path: Path) -> None:
    documents, report = ArchiveScanner(tmp_path).scan()
    assert documents == []
    assert report.total_count == 0
