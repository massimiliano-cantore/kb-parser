"""Tests for the knowledge base index."""

import json
from pathlib import Path

import pytest

from kb_parser.document import Document
from kb_parser.exceptions import IndexFileError
from kb_parser.index import INDEX_FORMAT_VERSION, KnowledgeBaseIndex
from kb_parser.scanner import SkippedFile


def make(path: str, title: str, content: str, date: str | None = None) -> Document:
    """Build a document for the tests."""
    return Document(
        title=title,
        date=date,
        word_count=len(content.split()),
        excerpt=content[:50],
        file_format=path.rsplit(".", 1)[-1],
        path=path,
        content=content,
    )


@pytest.fixture
def index() -> KnowledgeBaseIndex:
    """An index with a few documents and one skipped file."""
    return KnowledgeBaseIndex(
        [
            make("b/verbale.txt", "Verbale qualità", "Riunione sul filtro. Filtro guasto, filtro nuovo.",
                 "2025-03-12"),
            make("a/procedura.md", "Procedura cambio filtro", "Smontare il coperchio.", "2024-01-05"),
            make("c/ricambi.csv", "ricambi", "codice: A12; descrizione: Filtro aria"),
            make("c/pompa.txt", "Scheda pompa", "Pressione massima 6 bar, manutenzione annuale"),
        ],
        source_folder="archive",
        skipped=[SkippedFile("x.pdf", "unsupported format", "extension '.pdf' is not supported")],
    )


def test_len_and_get(index: KnowledgeBaseIndex) -> None:
    assert len(index) == 4
    assert index.get("c/pompa.txt").title == "Scheda pompa"
    assert index.get("c\\pompa.txt") is not None
    assert index.get("missing.txt") is None


def test_duplicate_path_is_rejected(index: KnowledgeBaseIndex) -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        index.add(make("c/pompa.txt", "Altro", "testo"))


@pytest.mark.parametrize(
    ("sort_by", "first_path"),
    [("path", "a/procedura.md"), ("title", "a/procedura.md"), ("date", "a/procedura.md"),
     ("words", "b/verbale.txt")],
)
def test_list_documents_sorting(index: KnowledgeBaseIndex, sort_by: str, first_path: str) -> None:
    assert index.list_documents(sort_by)[0].path == first_path


def test_documents_without_date_are_listed_last(index: KnowledgeBaseIndex) -> None:
    assert [doc.date for doc in index.list_documents("date")][-2:] == [None, None]


def test_invalid_sort_key(index: KnowledgeBaseIndex) -> None:
    with pytest.raises(ValueError):
        index.list_documents("size")


def test_search_is_case_insensitive_and_ranked(index: KnowledgeBaseIndex) -> None:
    results = index.search("FILTRO")
    assert [result.document.path for result in results] == [
        "a/procedura.md",      # in title
        "b/verbale.txt",       # 3 occurrences
        "c/ricambi.csv",       # 1 occurrence
    ]
    assert results[1].occurrences == 3


def test_search_finds_part_of_words(index: KnowledgeBaseIndex) -> None:
    assert [r.document.path for r in index.search("manut")] == ["c/pompa.txt"]


def test_search_snippet_marks_the_match(index: KnowledgeBaseIndex) -> None:
    snippet = index.search("guasto")[0].snippet
    assert "[guasto]" in snippet


def test_search_without_results(index: KnowledgeBaseIndex) -> None:
    assert index.search("inesistente") == []


def test_empty_search_is_rejected(index: KnowledgeBaseIndex) -> None:
    with pytest.raises(ValueError):
        index.search("   ")


@pytest.mark.parametrize("value", ["csv", ".CSV", " Csv "])
def test_filter_by_format(index: KnowledgeBaseIndex, value: str) -> None:
    assert [doc.path for doc in index.filter_by_format(value)] == ["c/ricambi.csv"]


def test_filter_unknown_format(index: KnowledgeBaseIndex) -> None:
    assert index.filter_by_format("pdf") == []
    assert index.formats() == ["csv", "md", "txt"]


def test_statistics(index: KnowledgeBaseIndex) -> None:
    stats = index.statistics(top=2)
    assert stats.document_count == 4
    assert stats.documents_by_format == {"txt": 2, "csv": 1, "md": 1}
    assert [doc.path for doc in stats.longest] == ["b/verbale.txt", "c/pompa.txt"]
    assert (stats.with_date, stats.without_date) == (2, 2)
    assert (stats.oldest_date, stats.newest_date) == ("2024-01-05", "2025-03-12")
    assert stats.skipped_by_reason == {"unsupported format": 1}
    assert stats.skipped_count == 1


def test_statistics_of_empty_index() -> None:
    stats = KnowledgeBaseIndex().statistics()
    assert stats.document_count == 0
    assert stats.average_words == 0.0
    assert stats.oldest_date is None


def test_save_and_load_round_trip(index: KnowledgeBaseIndex, tmp_path: Path) -> None:
    path = tmp_path / "index.json"
    index.save(path)
    loaded = KnowledgeBaseIndex.load(path)
    assert list(loaded) == list(index)
    assert loaded.skipped == index.skipped
    assert loaded.source_folder == "archive"
    assert loaded.created_at == index.created_at
    assert not (tmp_path / "index.json.tmp").exists()


def test_saved_json_is_readable(index: KnowledgeBaseIndex, tmp_path: Path) -> None:
    path = tmp_path / "index.json"
    index.save(path)
    text = path.read_text(encoding="utf-8")
    assert "qualità" in text  # not escaped as à
    assert json.loads(text)["format_version"] == INDEX_FORMAT_VERSION


def test_save_to_missing_folder(index: KnowledgeBaseIndex, tmp_path: Path) -> None:
    with pytest.raises(IndexFileError, match="cannot write"):
        index.save(tmp_path / "missing" / "index.json")


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{not json", "invalid JSON"),
        ("[1, 2]", "not a kb-parser index"),
        ('{"documents": []}', "version"),
        ('{"format_version": 99, "documents": []}', "version"),
        ('{"format_version": 1, "documents": {}}', "must be a list"),
        ('{"format_version": 1, "documents": [{"title": "x"}]}', "document #1"),
        ('{"format_version": 1, "documents": [], "skipped": [1]}', "skipped file #1"),
    ],
)
def test_load_invalid_index(tmp_path: Path, content: str, message: str) -> None:
    path = tmp_path / "index.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(IndexFileError, match=message):
        KnowledgeBaseIndex.load(path)


def test_load_missing_file(tmp_path: Path) -> None:
    with pytest.raises(IndexFileError, match="build"):
        KnowledgeBaseIndex.load(tmp_path / "index.json")


def test_load_duplicate_paths(index: KnowledgeBaseIndex, tmp_path: Path) -> None:
    data = index.to_dict()
    data["documents"].append(data["documents"][0])
    path = tmp_path / "index.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(IndexFileError, match="document #5"):
        KnowledgeBaseIndex.load(path)
