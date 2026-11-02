"""Exception hierarchy for kb_parser.

Every problem the parser knows how to handle has its own exception class,
all derived from ``KBParserError``. The scanner catches ``KBParserError``
once, records the file and the reason in the scan report and moves on to
the next file.
"""

from pathlib import Path


class KBParserError(Exception):
    """Base class for all errors raised by kb_parser.

    Attributes:
        path: The file or folder the error refers to.
        message: Human readable description of the problem.
        reason: Short label used to group errors in the scan report.
    """

    reason = "parser error"

    def __init__(self, path: Path, message: str) -> None:
        """Initialize the error.

        Args:
            path: The file or folder the error refers to.
            message: Human readable description of the problem.
        """
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


class UnsupportedFormatError(KBParserError):
    """The file extension is not handled by any registered reader."""

    reason = "unsupported format"


class EmptyDocumentError(KBParserError):
    """The file is empty or contains no usable text."""

    reason = "empty file"


class DocumentReadError(KBParserError):
    """The file cannot be read (missing, no permission, too large, I/O error)."""

    reason = "unreadable file"


class CorruptedContentError(KBParserError):
    """The file can be read but its content is malformed or binary."""

    reason = "corrupted content"


class InvalidArchiveError(KBParserError):
    """The archive folder given by the user does not exist or is not a folder."""

    reason = "invalid archive"


class IndexFileError(KBParserError):
    """The index file cannot be written, read or is not a valid index."""

    reason = "invalid index"
