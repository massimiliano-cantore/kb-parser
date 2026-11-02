"""Format readers and the extension-to-reader registry.

The registry maps each file extension to the reader that handles it.
To support a new format, write a ``BaseReader`` subclass and pass it to
``register_reader``: nothing else in the program needs to change.
"""

from pathlib import Path

from kb_parser.exceptions import UnsupportedFormatError
from kb_parser.readers.base import BaseReader
from kb_parser.readers.csv_reader import CsvReader
from kb_parser.readers.markdown_reader import MarkdownReader
from kb_parser.readers.txt_reader import TxtReader

__all__ = [
    "BaseReader",
    "CsvReader",
    "MarkdownReader",
    "TxtReader",
    "get_reader",
    "register_reader",
    "supported_extensions",
]

_registry: dict[str, BaseReader] = {}


def register_reader(reader_class: type[BaseReader]) -> None:
    """Register a reader for all the extensions it declares.

    Args:
        reader_class: A ``BaseReader`` subclass.

    Raises:
        ValueError: If the reader declares no extension, or an extension is
            already handled by another reader.
    """
    if not reader_class.extensions:
        raise ValueError(f"{reader_class.__name__} declares no extensions")
    reader = reader_class()
    for extension in reader_class.extensions:
        extension = extension.lower()
        if extension in _registry:
            other = type(_registry[extension]).__name__
            raise ValueError(f"Extension '{extension}' is already handled by {other}")
        _registry[extension] = reader


def get_reader(path: Path) -> BaseReader:
    """Return the reader for a file, chosen by its extension.

    The extension is compared case-insensitively, so ``.TXT`` works too.

    Args:
        path: The file to read.

    Returns:
        The reader that handles the file extension.

    Raises:
        UnsupportedFormatError: If no reader handles the extension.
    """
    extension = path.suffix.lower()
    if not extension:
        raise UnsupportedFormatError(path, "the file has no extension")
    try:
        return _registry[extension]
    except KeyError:
        raise UnsupportedFormatError(
            path,
            f"extension '{extension}' is not supported "
            f"(supported: {', '.join(supported_extensions())})",
        ) from None


def supported_extensions() -> list[str]:
    """List the extensions handled by the registered readers.

    Returns:
        The extensions, sorted alphabetically.
    """
    return sorted(_registry)


for _reader_class in (TxtReader, MarkdownReader, CsvReader):
    register_reader(_reader_class)
