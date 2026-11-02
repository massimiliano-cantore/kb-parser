"""Regression test: the sample archive delivered with the project."""

from pathlib import Path

from kb_parser.scanner import ArchiveScanner

SAMPLE_ARCHIVE = Path(__file__).resolve().parent.parent / "sample_archive"


def test_sample_archive_scan() -> None:
    documents, report = ArchiveScanner(SAMPLE_ARCHIVE).scan()
    assert report.processed_count == 14
    assert {item.path: item.reason for item in report.skipped} == {
        "backup_corrotto.txt": "corrupted content",
        "file_vuoto.txt": "empty file",
        "manuale_piattaforma.pdf": "unsupported format",
        "registro_presenze_rotto.csv": "corrupted content",
    }
    by_path = {document.path: document for document in documents}
    assert "perché" in by_path["verbali/verbale_collegio_docenti_2024.txt"].content
    assert "3.200 €" in by_path["schede_tecniche/fornitori_windows.csv"].content
    assert by_path["note/appunti_riunione_fornitori.md"].title == "appunti_riunione_fornitori"
    assert ".bozza_nascosta.txt" not in by_path
