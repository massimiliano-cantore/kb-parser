"""Folder scanning and scan report.

``ArchiveScanner`` walks the archive folder and its subfolders, reads every
file with the right reader and collects the resulting documents. A file
that cannot be processed never stops the scan: it is recorded in the
``ScanReport`` with the reason, and the scan moves on to the next file.
"""

import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from kb_parser.document import Document
from kb_parser.exceptions import DocumentReadError, InvalidArchiveError, KBParserError
from kb_parser.readers import get_reader

UNEXPECTED_ERROR_REASON = "unexpected error"


@dataclass(frozen=True)
class SkippedFile:
    """A file that could not be processed.

    Attributes:
        path: File path relative to the archive folder.
        reason: Short label used to group the errors (e.g. ``"empty file"``).
        message: Detailed description of the problem.
    """

    path: str
    reason: str
    message: str


@dataclass
class ScanReport:
    """Summary of a scan: processed files, skipped files and reasons.

    Attributes:
        root: The scanned archive folder.
        processed: Relative paths of the files turned into documents.
        skipped: The files that could not be processed.
    """

    root: Path
    processed: list[str] = field(default_factory=list)
    skipped: list[SkippedFile] = field(default_factory=list)

    @property
    def processed_count(self) -> int:
        """Number of files successfully turned into documents."""
        return len(self.processed)

    @property
    def skipped_count(self) -> int:
        """Number of files that could not be processed."""
        return len(self.skipped)

    @property
    def total_count(self) -> int:
        """Number of files found in the archive (hidden files excluded)."""
        return self.processed_count + self.skipped_count

    def skipped_by_reason(self) -> dict[str, int]:
        """Count the skipped files for each reason.

        Returns:
            Reason to count mapping, most frequent reasons first.
        """
        return dict(Counter(item.reason for item in self.skipped).most_common())

    def summary(self) -> str:
        """Build a human readable summary of the scan.

        Returns:
            A multi-line text with the counts and the list of skipped files
            with their reasons. The caller decides how to display it.
        """
        lines = [
            f"Archive: {self.root}",
            f"Files found: {self.total_count}",
            f"Processed:   {self.processed_count}",
            f"Skipped:     {self.skipped_count}",
        ]
        for reason, count in self.skipped_by_reason().items():
            lines.append(f"  - {reason}: {count}")
        if self.skipped:
            lines.append("")
            lines.append("Skipped files:")
            for item in self.skipped:
                lines.append(f"  - {item.path} [{item.reason}] {item.message}")
        return "\n".join(lines)


class ArchiveScanner:
    """Walks an archive folder and turns every supported file into a document.

    The scan is recursive and deterministic (folders and files are visited
    in alphabetical order). Hidden files and folders, whose name starts with
    a dot, are ignored. Symbolic links to folders are not followed, to avoid
    endless loops.
    """

    def __init__(self, root: Path | str) -> None:
        """Initialize the scanner.

        Args:
            root: The archive folder to scan.
        """
        self.root = Path(root)

    def scan(self) -> tuple[list[Document], ScanReport]:
        """Scan the archive and read all the files.

        Returns:
            The documents read successfully and the scan report.

        Raises:
            InvalidArchiveError: If the archive folder does not exist or is
                not a folder. This is the only error that stops the scan.
        """
        self._check_root()
        documents: list[Document] = []
        report = ScanReport(root=self.root)

        for path in self._iter_files(report):
            relative = path.relative_to(self.root).as_posix()
            try:
                document = get_reader(path).read(path, root=self.root)
            except KBParserError as error:
                report.skipped.append(SkippedFile(relative, error.reason, error.message))
            except Exception as error:  # noqa: BLE001
                # An archive we have never seen may contain cases nobody
                # anticipated. The error is not hidden: it is recorded with
                # its type, and the scan continues with the other files.
                report.skipped.append(
                    SkippedFile(
                        relative,
                        UNEXPECTED_ERROR_REASON,
                        f"{type(error).__name__}: {error}",
                    )
                )
            else:
                documents.append(document)
                report.processed.append(relative)

        return documents, report

    def _check_root(self) -> None:
        """Verify that the archive folder exists and is a folder.

        Raises:
            InvalidArchiveError: If the folder is missing or is a file.
        """
        if not self.root.exists():
            raise InvalidArchiveError(self.root, "the archive folder does not exist")
        if not self.root.is_dir():
            raise InvalidArchiveError(self.root, "the archive path is not a folder")

    def _iter_files(self, report: ScanReport) -> list[Path]:
        """List the files to process, in alphabetical order.

        Folders that cannot be opened are recorded in the report as
        unreadable instead of stopping the scan.

        Args:
            report: The report where unreadable folders are recorded.

        Returns:
            The paths of the non-hidden files in the archive.
        """

        def on_error(error: OSError) -> None:
            folder = Path(error.filename) if error.filename else self.root
            failure = DocumentReadError(folder, f"cannot open folder ({error.strerror})")
            report.skipped.append(
                SkippedFile(_relative_or_full(folder, self.root), failure.reason, failure.message)
            )

        files: list[Path] = []
        for folder, subfolders, filenames in os.walk(self.root, onerror=on_error):
            # Sorting in place also fixes the order in which os.walk descends.
            subfolders[:] = sorted(name for name in subfolders if not _is_hidden(name))
            files.extend(
                Path(folder) / name for name in sorted(filenames) if not _is_hidden(name)
            )
        return files


def _is_hidden(name: str) -> bool:
    """Tell whether a file or folder name is hidden.

    Args:
        name: The file or folder name.

    Returns:
        ``True`` if the name starts with a dot.
    """
    return name.startswith(".")


def _relative_or_full(path: Path, root: Path) -> str:
    """Express a path relative to the archive folder when possible.

    Args:
        path: The path to express.
        root: The archive folder.

    Returns:
        The relative path with forward slashes, or the full path.
    """
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
