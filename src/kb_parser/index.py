"""Knowledge base index: search, filters, statistics and JSON persistence.

``KnowledgeBaseIndex`` keeps the documents produced by the scanner and
answers the questions the knowledge base is built for: list the
documents, search them, filter them by format and summarize the archive.
It can be saved to a JSON file and loaded back without parsing the
original files again.
"""

import json
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from kb_parser.document import Document
from kb_parser.exceptions import IndexFileError
from kb_parser.scanner import ScanReport, SkippedFile

INDEX_FORMAT_VERSION = 1
SORT_KEYS = ("path", "title", "date", "words")
DEFAULT_TOP = 5
SNIPPET_RADIUS = 60


@dataclass(frozen=True)
class SearchResult:
    """A document matching a search, with the data used to rank it.

    Attributes:
        document: The matching document.
        in_title: ``True`` if the keyword appears in the title.
        occurrences: Number of times the keyword appears in the content.
        snippet: Text around the first occurrence, with the match in
            square brackets.
    """

    document: Document
    in_title: bool
    occurrences: int
    snippet: str


@dataclass(frozen=True)
class IndexStatistics:
    """Summary figures of the knowledge base.

    Attributes:
        document_count: Number of indexed documents.
        total_words: Total number of words in all the documents.
        average_words: Average number of words per document.
        documents_by_format: Number of documents for each format.
        longest: The longest documents, longest first.
        with_date: Number of documents with a date.
        without_date: Number of documents without a date.
        oldest_date: Oldest document date, or ``None``.
        newest_date: Most recent document date, or ``None``.
        skipped_by_reason: Files skipped at build time, counted by reason.
    """

    document_count: int
    total_words: int
    average_words: float
    documents_by_format: dict[str, int]
    longest: tuple[Document, ...]
    with_date: int
    without_date: int
    oldest_date: str | None
    newest_date: str | None
    skipped_by_reason: dict[str, int]

    @property
    def skipped_count(self) -> int:
        """Number of files skipped at build time."""
        return sum(self.skipped_by_reason.values())


class KnowledgeBaseIndex:
    """The searchable collection of the documents of an archive.

    Attributes:
        source_folder: The archive folder the index was built from.
        created_at: Creation time in ISO format.
    """

    def __init__(
        self,
        documents: list[Document] | None = None,
        source_folder: str | None = None,
        created_at: str | None = None,
        skipped: list[SkippedFile] | None = None,
    ) -> None:
        """Initialize the index.

        Args:
            documents: The documents to index.
            source_folder: The archive folder the documents come from.
            created_at: Creation time in ISO format; defaults to now.
            skipped: Files that could not be processed at build time.

        Raises:
            ValueError: If two documents have the same path.
        """
        self._documents: list[Document] = []
        self._by_path: dict[str, Document] = {}
        for document in documents or []:
            self.add(document)
        self.source_folder = source_folder
        self.created_at = created_at or datetime.now().isoformat(timespec="seconds")
        self._skipped: list[SkippedFile] = list(skipped or [])

    @classmethod
    def from_scan(cls, documents: list[Document], report: ScanReport) -> "KnowledgeBaseIndex":
        """Build an index from the result of an archive scan.

        Args:
            documents: The documents returned by the scanner.
            report: The scan report, whose skipped files are kept in the index.

        Returns:
            The new index.
        """
        return cls(documents, source_folder=report.root.as_posix(), skipped=report.skipped)

    def add(self, document: Document) -> None:
        """Add a document to the index.

        Args:
            document: The document to add.

        Raises:
            ValueError: If a document with the same path is already indexed.
        """
        if document.path in self._by_path:
            raise ValueError(f"Duplicate document path: {document.path}")
        self._documents.append(document)
        self._by_path[document.path] = document

    def __len__(self) -> int:
        """Return the number of indexed documents."""
        return len(self._documents)

    def __iter__(self) -> Iterator[Document]:
        """Iterate over the documents in insertion order."""
        return iter(self._documents)

    @property
    def skipped(self) -> list[SkippedFile]:
        """Files skipped when the index was built (a copy)."""
        return list(self._skipped)

    def get(self, path: str) -> Document | None:
        """Return the document with the given path.

        Args:
            path: The document path, as stored in the index.

        Returns:
            The document, or ``None`` if no document has that path.
        """
        return self._by_path.get(path.replace("\\", "/"))

    def formats(self) -> list[str]:
        """List the formats present in the index.

        Returns:
            The formats, sorted alphabetically.
        """
        return sorted({document.file_format for document in self._documents})

    def list_documents(self, sort_by: str = "path") -> list[Document]:
        """List all the documents in the requested order.

        Args:
            sort_by: ``"path"`` and ``"title"`` sort alphabetically,
                ``"date"`` from the oldest (documents without a date last),
                ``"words"`` from the longest.

        Returns:
            The sorted documents.

        Raises:
            ValueError: If ``sort_by`` is not one of ``SORT_KEYS``.
        """
        if sort_by == "path":
            return sorted(self._documents, key=lambda doc: doc.path.casefold())
        if sort_by == "title":
            return sorted(self._documents, key=lambda doc: (doc.title.casefold(), doc.path))
        if sort_by == "date":
            return sorted(
                self._documents, key=lambda doc: (doc.date is None, doc.date or "", doc.path)
            )
        if sort_by == "words":
            return sorted(self._documents, key=lambda doc: (-doc.word_count, doc.path))
        raise ValueError(f"Invalid sort key '{sort_by}' (allowed: {', '.join(SORT_KEYS)})")

    def search(self, keyword: str) -> list[SearchResult]:
        """Find the documents containing a keyword in the title or content.

        The match is case-insensitive and also finds parts of words
        (``"manut"`` finds ``"manutenzione"``). Results are ranked by
        relevance: documents with the keyword in the title first, then by
        number of occurrences in the content.

        Args:
            keyword: The text to look for.

        Returns:
            The matching documents, most relevant first.

        Raises:
            ValueError: If the keyword is empty.
        """
        keyword = unicodedata.normalize("NFC", keyword.strip())
        if not keyword:
            raise ValueError("The search keyword must not be empty")
        needle = keyword.casefold()

        results = []
        for document in self._documents:
            in_title = needle in document.title.casefold()
            occurrences = document.content.casefold().count(needle)
            if in_title or occurrences:
                results.append(
                    SearchResult(
                        document=document,
                        in_title=in_title,
                        occurrences=occurrences,
                        snippet=_make_snippet(document, keyword),
                    )
                )
        results.sort(key=lambda result: (not result.in_title, -result.occurrences,
                                         result.document.path))
        return results

    def filter_by_format(self, file_format: str) -> list[Document]:
        """Return the documents of one format.

        Args:
            file_format: The format, with or without the dot and in any case
                (``"csv"``, ``".CSV"``).

        Returns:
            The documents of that format, sorted by path.

        Raises:
            ValueError: If the format is empty.
        """
        wanted = file_format.strip().lower().lstrip(".")
        if not wanted:
            raise ValueError("The format must not be empty")
        return [doc for doc in self.list_documents() if doc.file_format == wanted]

    def statistics(self, top: int = DEFAULT_TOP) -> IndexStatistics:
        """Compute summary statistics of the knowledge base.

        Args:
            top: How many of the longest documents to include.

        Returns:
            The statistics.

        Raises:
            ValueError: If ``top`` is less than 1.
        """
        if top < 1:
            raise ValueError("The number of longest documents must be at least 1")
        count = len(self._documents)
        total_words = sum(doc.word_count for doc in self._documents)
        dates = sorted(doc.date for doc in self._documents if doc.date)
        by_format = Counter(doc.file_format for doc in self._documents)
        skipped = Counter(item.reason for item in self._skipped)
        return IndexStatistics(
            document_count=count,
            total_words=total_words,
            average_words=total_words / count if count else 0.0,
            documents_by_format=dict(sorted(by_format.items(), key=lambda item: (-item[1], item[0]))),
            longest=tuple(self.list_documents(sort_by="words")[:top]),
            with_date=len(dates),
            without_date=count - len(dates),
            oldest_date=dates[0] if dates else None,
            newest_date=dates[-1] if dates else None,
            skipped_by_reason=dict(skipped.most_common()),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert the index into a JSON-serializable dictionary.

        Returns:
            The index data, including format version and metadata.
        """
        return {
            "format_version": INDEX_FORMAT_VERSION,
            "created_at": self.created_at,
            "source_folder": self.source_folder,
            "document_count": len(self._documents),
            "documents": [document.to_dict() for document in self._documents],
            "skipped": [asdict(item) for item in self._skipped],
        }

    def save(self, path: Path | str) -> None:
        """Save the index to a JSON file.

        The data is written to a temporary file that then replaces the
        target, so an interrupted save never leaves a half-written index.

        Args:
            path: The index file to write.

        Raises:
            IndexFileError: If the file cannot be written.
        """
        path = Path(path)
        temporary = path.with_name(path.name + ".tmp")
        text = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        try:
            temporary.write_text(text + "\n", encoding="utf-8")
            temporary.replace(path)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise IndexFileError(
                path, f"cannot write the index file ({error.strerror})"
            ) from None

    @classmethod
    def load(cls, path: Path | str) -> "KnowledgeBaseIndex":
        """Load an index saved with ``save``, without parsing the archive again.

        Args:
            path: The index file to read.

        Returns:
            The loaded index.

        Raises:
            IndexFileError: If the file is missing, unreadable, not valid
                JSON or not a valid index.
        """
        path = Path(path)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise IndexFileError(
                path, "the index file does not exist, run the 'build' command first"
            ) from None
        except UnicodeDecodeError:
            raise IndexFileError(path, "the index file is not UTF-8 text") from None
        except OSError as error:
            raise IndexFileError(
                path, f"cannot read the index file ({error.strerror})"
            ) from None

        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise IndexFileError(
                path, f"invalid JSON at line {error.lineno}, column {error.colno}"
            ) from None
        return cls._from_dict(data, path)

    @classmethod
    def _from_dict(cls, data: Any, path: Path) -> "KnowledgeBaseIndex":
        """Rebuild an index from the data read from a JSON file.

        Args:
            data: The decoded JSON content.
            path: The index file, used in error messages.

        Returns:
            The rebuilt index.

        Raises:
            IndexFileError: If the data is not a valid index.
        """
        if not isinstance(data, dict) or "documents" not in data:
            raise IndexFileError(path, "the file is not a kb-parser index")
        version = data.get("format_version")
        if version != INDEX_FORMAT_VERSION:
            raise IndexFileError(
                path,
                f"unsupported index format version {version!r} "
                f"(expected {INDEX_FORMAT_VERSION}), rebuild the index",
            )
        if not isinstance(data["documents"], list):
            raise IndexFileError(path, "'documents' must be a list")

        index = cls(
            source_folder=_optional_string(data, "source_folder", path),
            created_at=_optional_string(data, "created_at", path),
            skipped=_load_skipped(data.get("skipped", []), path),
        )
        for number, entry in enumerate(data["documents"], start=1):
            try:
                index.add(Document.from_dict(entry))
            except ValueError as error:
                raise IndexFileError(path, f"document #{number}: {error}") from None
        return index


def _make_snippet(document: Document, keyword: str) -> str:
    """Build a short text around the first occurrence of a keyword.

    Args:
        document: The document containing the keyword.
        keyword: The keyword, as typed by the user.

    Returns:
        About ``SNIPPET_RADIUS`` characters on each side of the first
        occurrence, with the match in square brackets. If the keyword is
        only in the title, the document excerpt.
    """
    match = re.search(re.escape(keyword), document.content, re.IGNORECASE)
    if match is None:
        return document.excerpt
    start = max(0, match.start() - SNIPPET_RADIUS)
    end = min(len(document.content), match.end() + SNIPPET_RADIUS)
    content = document.content
    marked = f"{content[start:match.start()]}[{match.group()}]{content[match.end():end]}"
    snippet = " ".join(marked.split())
    if start > 0:
        snippet = "…" + snippet
    if end < len(document.content):
        snippet += "…"
    return snippet


def _optional_string(data: dict[str, Any], key: str, path: Path) -> str | None:
    """Read an optional string value from the index data.

    Args:
        data: The index data.
        key: The key to read.
        path: The index file, used in error messages.

    Returns:
        The value, or ``None`` if missing.

    Raises:
        IndexFileError: If the value is present but not a string.
    """
    value = data.get(key)
    if value is not None and not isinstance(value, str):
        raise IndexFileError(path, f"'{key}' must be a string")
    return value


def _load_skipped(entries: Any, path: Path) -> list[SkippedFile]:
    """Rebuild the list of skipped files from the index data.

    Args:
        entries: The ``skipped`` value read from JSON.
        path: The index file, used in error messages.

    Returns:
        The skipped files.

    Raises:
        IndexFileError: If the entries are malformed.
    """
    if not isinstance(entries, list):
        raise IndexFileError(path, "'skipped' must be a list")
    skipped = []
    for number, entry in enumerate(entries, start=1):
        fields_ok = isinstance(entry, dict) and all(
            isinstance(entry.get(key), str) for key in ("path", "reason", "message")
        )
        if not fields_ok:
            raise IndexFileError(path, f"skipped file #{number} is malformed")
        skipped.append(SkippedFile(entry["path"], entry["reason"], entry["message"]))
    return skipped
