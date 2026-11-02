"""Abstract base class for all format readers.

``BaseReader.read`` implements the steps shared by every format (template
method pattern): reading the bytes, decoding, empty and binary checks,
title fallback, word count, excerpt and date extraction. Concrete readers
only implement ``parse``, the part that depends on the format.
"""

import re
import unicodedata
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path

from kb_parser.document import Document
from kb_parser.exceptions import (
    CorruptedContentError,
    DocumentReadError,
    EmptyDocumentError,
)

EXCERPT_LENGTH = 200
TITLE_MAX_LENGTH = 120
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

# Share of control characters above which a decoded text is considered binary.
_MAX_CONTROL_RATIO = 0.05
# Control characters (Unicode category Cc) except tab, newlines, \v, \f and \r,
# which are normal in a text file.
_BINARY_CONTROLS = re.compile(r"[\x00-\x08\x0e-\x1f\x7f-\x9f]")
# Every control character except tab and newline, removed from the content.
_CONTENT_CONTROLS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
# Invisible formatting characters (zero-width spaces, misplaced BOM).
_INVISIBLE = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff]")
_HORIZONTAL_SPACE = re.compile(r"[ \t\u00a0]{2,}|[\t\u00a0]")
_SPACE_AROUND_NEWLINE = re.compile(r" *\n *")
_EXTRA_BLANK_LINES = re.compile(r"\n{3,}")

_UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")

# One pattern per format, each starting with a digit and without look-behind:
# this lets the regex engine skip quickly over long texts. "Not preceded by
# a digit" is checked in _first_valid_date.
_ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?!\d)")
_EU_DATE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)")


class BaseReader(ABC):
    """Common interface and shared reading logic for all format readers.

    Subclasses declare the extensions they handle in ``extensions`` and
    implement ``parse``. Adding a new format means writing a new subclass
    and registering it, without touching the rest of the program.

    Attributes:
        extensions: Lowercase file extensions handled by the reader,
            including the leading dot (e.g. ``(".txt",)``).
    """

    extensions: tuple[str, ...] = ()

    def read(self, path: Path, root: Path | None = None) -> Document:
        """Read a file and turn it into a normalized ``Document``.

        Args:
            path: The file to read.
            root: Archive folder. When given, the document path is stored
                relative to it, so the index does not depend on the machine.

        Returns:
            The normalized document.

        Raises:
            DocumentReadError: If the file cannot be read or is too large.
            EmptyDocumentError: If the file contains no usable text.
            CorruptedContentError: If the content is binary or malformed.
        """
        raw = self._read_bytes(path)
        if not raw:
            raise EmptyDocumentError(path, "the file is empty")
        if not raw.strip():
            raise EmptyDocumentError(path, "the file contains only whitespace")

        text = self._decode(raw, path)
        if not text.strip():
            raise EmptyDocumentError(path, "the file contains only whitespace")

        title, content = self.parse(text, path)
        content = _normalize_whitespace(content)
        if not content:
            raise EmptyDocumentError(path, "the file contains no textual content")

        return Document(
            title=_clean_title(title) or path.stem,
            date=_find_date(content),
            word_count=len(content.split()),
            excerpt=_make_excerpt(content),
            file_format=path.suffix.lower().lstrip("."),
            path=_relative_path(path, root),
            content=content,
        )

    @abstractmethod
    def parse(self, text: str, path: Path) -> tuple[str | None, str]:
        """Extract title and content from the decoded text of a file.

        Args:
            text: The decoded file text, with ``\\n`` line endings.
            path: The file being read, used in error messages.

        Returns:
            A ``(title, content)`` tuple. ``title`` is ``None`` when the
            format does not provide one; the file name is then used.

        Raises:
            CorruptedContentError: If the content does not respect the format.
            EmptyDocumentError: If the format has no usable content.
        """

    @staticmethod
    def _read_bytes(path: Path) -> bytes:
        """Read the raw bytes of a file, converting OS errors.

        Args:
            path: The file to read.

        Returns:
            The file content as bytes.

        Raises:
            DocumentReadError: If the file cannot be read or is too large.
        """
        try:
            size = path.stat().st_size
            if size > MAX_FILE_SIZE:
                raise DocumentReadError(
                    path,
                    f"the file is too large ({size // (1024 * 1024)} MB, "
                    f"limit {MAX_FILE_SIZE // (1024 * 1024)} MB)",
                )
            return path.read_bytes()
        except PermissionError:
            raise DocumentReadError(path, "permission denied") from None
        except FileNotFoundError:
            raise DocumentReadError(path, "the file no longer exists") from None
        except IsADirectoryError:
            raise DocumentReadError(path, "the path is a folder, not a file") from None
        except OSError as error:
            raise DocumentReadError(path, f"I/O error ({error.strerror})") from None

    @staticmethod
    def _decode(raw: bytes, path: Path) -> str:
        """Decode bytes into text, trying the most likely encodings in order.

        Order: UTF-16 (only with BOM), UTF-8 (with or without BOM),
        Windows-1252, Latin-1. Latin-1 never fails, so the result is then
        checked to reject binary files disguised as text.

        Args:
            raw: The file bytes.
            path: The file being read, used in error messages.

        Returns:
            The decoded text, NFC-normalized and with ``\\n`` line endings.

        Raises:
            CorruptedContentError: If the content looks binary.
        """
        text = None
        if raw.startswith(_UTF16_BOMS):
            try:
                text = raw.decode("utf-16")
            except UnicodeDecodeError:
                raise CorruptedContentError(path, "invalid UTF-16 text") from None
        else:
            if b"\x00" in raw:
                raise CorruptedContentError(
                    path, "the file contains null bytes, it looks like a binary file"
                )
            for encoding in ("utf-8-sig", "cp1252", "latin-1"):
                try:
                    text = raw.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue

        if text is None or _looks_binary(text):
            raise CorruptedContentError(
                path, "the content is not readable text, it looks like a binary file"
            )

        text = text.replace("\r\n", "\n").replace("\r", "\n")
        return unicodedata.normalize("NFC", text)


def _looks_binary(text: str) -> bool:
    """Tell whether a decoded text contains too many control characters.

    Args:
        text: The decoded text.

    Returns:
        ``True`` if the text is probably a decoded binary file.
    """
    if "\x00" in text:
        return True
    controls = sum(1 for _ in _BINARY_CONTROLS.finditer(text))
    return controls / len(text) > _MAX_CONTROL_RATIO


def _normalize_whitespace(text: str) -> str:
    """Normalize spaces and blank lines, keeping paragraph breaks.

    Removes leftover control and invisible characters, collapses runs of
    spaces and tabs, strips each line and keeps at most one blank line
    between paragraphs. Regular expressions are used instead of a
    character-by-character loop so that very long files stay fast.

    Args:
        text: The text to normalize.

    Returns:
        The normalized text.
    """
    text = _CONTENT_CONTROLS.sub(" ", text)
    text = _INVISIBLE.sub("", text)
    text = _HORIZONTAL_SPACE.sub(" ", text)
    text = _SPACE_AROUND_NEWLINE.sub("\n", text)
    text = _EXTRA_BLANK_LINES.sub("\n\n", text)
    return text.strip()


def _clean_title(title: str | None) -> str:
    """Collapse whitespace in a title and shorten it if too long.

    Args:
        title: The raw title, or ``None``.

    Returns:
        The cleaned title, or an empty string if there is none.
    """
    if title is None:
        return ""
    title = " ".join(title.split())
    if len(title) > TITLE_MAX_LENGTH:
        title = title[:TITLE_MAX_LENGTH].rsplit(" ", 1)[0] + "…"
    return title


def _make_excerpt(content: str) -> str:
    """Build a short single-line excerpt of the content.

    Args:
        content: The normalized content.

    Returns:
        About ``EXCERPT_LENGTH`` characters, cut at the end of a word,
        followed by ``…`` if the content is longer.
    """
    flat = " ".join(content.split())
    if len(flat) <= EXCERPT_LENGTH:
        return flat
    cut = flat[:EXCERPT_LENGTH]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" .,;:") + "…"


def _find_date(text: str) -> str | None:
    """Find the first valid date in the text.

    Recognized formats are ``YYYY-MM-DD`` and ``DD/MM/YYYY``. Impossible
    dates such as ``31/02/2025`` are ignored.

    Args:
        text: The text to search.

    Returns:
        The first valid date in ISO format, or ``None`` if there is none.
    """
    candidates = [
        found
        for found in (
            _first_valid_date(_ISO_DATE, text, year_first=True),
            _first_valid_date(_EU_DATE, text, year_first=False),
        )
        if found is not None
    ]
    if not candidates:
        return None
    return min(candidates)[1]


def _first_valid_date(
    pattern: re.Pattern[str], text: str, year_first: bool
) -> tuple[int, str] | None:
    """Find the first valid date matching one date pattern.

    Args:
        pattern: Compiled pattern with three groups.
        text: The text to search.
        year_first: ``True`` if the groups are year, month, day;
            ``False`` if they are day, month, year.

    Returns:
        The position of the date in the text and the date in ISO format,
        or ``None`` if no valid date matches.
    """
    for match in pattern.finditer(text):
        if match.start() > 0 and text[match.start() - 1].isdigit():
            continue
        first, month, last = (int(group) for group in match.groups())
        year, day = (first, last) if year_first else (last, first)
        try:
            return match.start(), date(year, month, day).isoformat()
        except ValueError:
            continue
    return None


def _relative_path(path: Path, root: Path | None) -> str:
    """Express a file path relative to the archive folder.

    Args:
        path: The file path.
        root: The archive folder, or ``None``.

    Returns:
        The path with forward slashes, relative to ``root`` when possible.
    """
    if root is not None:
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            pass
    return path.as_posix()
