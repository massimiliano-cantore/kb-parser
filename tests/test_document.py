"""Tests for the Document model."""

import json

import pytest

from kb_parser.document import Document


def make_document() -> Document:
    """Build a sample document."""
    return Document(
        title="Procedura cambio filtro",
        date="2025-03-12",
        word_count=4,
        excerpt="Questa procedura descrive",
        file_format="md",
        path="procedure/filtro.md",
        content="Questa procedura descrive tutto",
    )


def test_round_trip_through_json() -> None:
    document = make_document()
    loaded = json.loads(json.dumps(document.to_dict()))
    assert Document.from_dict(loaded) == document


def test_missing_field_is_reported() -> None:
    data = make_document().to_dict()
    del data["content"]
    with pytest.raises(ValueError, match="content"):
        Document.from_dict(data)


@pytest.mark.parametrize("value", ["4", True, -1, 4.0])
def test_invalid_word_count_is_rejected(value: object) -> None:
    data = {**make_document().to_dict(), "word_count": value}
    with pytest.raises(ValueError):
        Document.from_dict(data)


def test_extra_keys_are_ignored() -> None:
    data = {**make_document().to_dict(), "future_field": 1}
    assert Document.from_dict(data) == make_document()


def test_document_is_immutable() -> None:
    document = make_document()
    with pytest.raises(AttributeError):
        document.title = "Other"  # type: ignore[misc]
