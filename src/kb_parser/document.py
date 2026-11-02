"""Normalized document model shared by all readers.

Every reader, whatever the source format, turns a file into a ``Document``.
From that point on the rest of the program (index, search, statistics,
persistence) works only with ``Document`` objects and never needs to know
how the original file was written.
"""

from dataclasses import asdict, dataclass, fields
from typing import Any


@dataclass(frozen=True)
class Document:
    """A knowledge base document in normalized form.

    A ``Document`` is the common "index card" produced by every reader.
    It is immutable (``frozen=True``): once a file has been parsed, its card
    cannot be changed by mistake elsewhere in the program.

    Attributes:
        title: Document title. Taken from the content when possible,
            otherwise from the file name.
        date: First date found in the text, in ISO format ``YYYY-MM-DD``,
            or ``None`` if the text contains no date.
        word_count: Number of words in the normalized content.
        excerpt: Short excerpt of the content, used for previews.
        file_format: Source format, lowercase and without the dot
            (e.g. ``"txt"``, ``"md"``, ``"csv"``).
        path: Path of the source file, with forward slashes.
        content: Full normalized text of the document.
    """

    title: str
    date: str | None
    word_count: int
    excerpt: str
    file_format: str
    path: str
    content: str

    def to_dict(self) -> dict[str, Any]:
        """Convert the document into a JSON-serializable dictionary.

        Returns:
            A dictionary with one key per field. All values are strings,
            integers or ``None``, so it can be written with ``json.dump``.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Document":
        """Rebuild a document from a dictionary loaded from JSON.

        Keys that do not correspond to a field are ignored, so an index
        written by a newer version of the program can still be loaded.

        Args:
            data: Dictionary produced by ``to_dict`` and read back from
                the index file.

        Returns:
            The rebuilt ``Document``.

        Raises:
            ValueError: If ``data`` is not a dictionary, a required field
                is missing, or a field has the wrong type.
        """
        if not isinstance(data, dict):
            raise ValueError(
                f"Invalid document entry: expected an object, got {type(data).__name__}"
            )

        field_names = [field.name for field in fields(cls)]
        missing = [name for name in field_names if name not in data]
        if missing:
            raise ValueError(
                f"Invalid document entry: missing field(s) {', '.join(missing)}"
            )

        values = {name: data[name] for name in field_names}
        _check_types(values)
        return cls(**values)


def _check_types(values: dict[str, Any]) -> None:
    """Verify that the values loaded from JSON have the expected types.

    Args:
        values: Field name to value mapping, one entry per ``Document`` field.

    Raises:
        ValueError: If a value has the wrong type.
    """
    text_fields = ("title", "excerpt", "file_format", "path", "content")
    for name in text_fields:
        if not isinstance(values[name], str):
            raise ValueError(_type_error(name, "a string", values[name]))

    if values["date"] is not None and not isinstance(values["date"], str):
        raise ValueError(_type_error("date", "a string or null", values["date"]))

    # bool is a subclass of int in Python, so it must be excluded explicitly.
    word_count = values["word_count"]
    if isinstance(word_count, bool) or not isinstance(word_count, int):
        raise ValueError(_type_error("word_count", "an integer", word_count))
    if word_count < 0:
        raise ValueError(f"Invalid document entry: word_count is negative ({word_count})")


def _type_error(name: str, expected: str, value: Any) -> str:
    """Build the message for a field that has the wrong type.

    Args:
        name: Field name.
        expected: Human readable description of the expected type.
        value: The value actually found.

    Returns:
        The error message.
    """
    return (
        f"Invalid document entry: field '{name}' should be {expected}, "
        f"got {type(value).__name__}"
    )
