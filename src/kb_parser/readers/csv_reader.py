"""Reader for CSV (.csv) files."""

import csv
import io
from pathlib import Path

from kb_parser.exceptions import CorruptedContentError, EmptyDocumentError
from kb_parser.readers.base import BaseReader

_CANDIDATE_DELIMITERS = ",;\t|"
_SNIFF_LINES = 20


class CsvReader(BaseReader):
    """Reads CSV files and turns each row into a readable line of text.

    The delimiter is detected automatically (Italian CSV files often use
    ``;``). The first non-empty row is the header; every data row becomes
    ``column: value; column: value``. A CSV has no natural title, so the
    file name is used.

    A row with a different number of fields than the header makes the
    whole file invalid: misaligned columns would produce wrong data.
    """

    extensions = (".csv",)

    def parse(self, text: str, path: Path) -> tuple[str | None, str]:
        """Extract the content of a CSV file as text.

        Args:
            text: The decoded file text.
            path: The file being read.

        Returns:
            ``None`` as title and one text line per data row as content.

        Raises:
            CorruptedContentError: If the CSV syntax is invalid or a row has
                the wrong number of fields.
            EmptyDocumentError: If the file has a header but no data rows.
        """
        dialect = _detect_dialect(text)
        reader = csv.reader(io.StringIO(text), dialect, strict=True)

        header: list[str] | None = None
        lines: list[str] = []
        try:
            for row in reader:
                if not any(cell.strip() for cell in row):
                    continue
                if header is None:
                    header = _clean_header(row)
                    continue
                if len(row) != len(header):
                    raise CorruptedContentError(
                        path,
                        f"line {reader.line_num} has {len(row)} fields, "
                        f"expected {len(header)} as in the header",
                    )
                lines.append(_row_to_text(header, row))
        except csv.Error as error:
            raise CorruptedContentError(
                path, f"invalid CSV syntax at line {reader.line_num} ({error})"
            ) from None

        if not lines:
            raise EmptyDocumentError(path, "the CSV file has no data rows")
        return None, "\n".join(lines)


def _detect_dialect(text: str) -> type[csv.Dialect] | csv.Dialect:
    """Detect the CSV dialect (mainly the delimiter) from the first lines.

    ``csv.Sniffer`` is tried first. It fails when rows are inconsistent,
    which is exactly the case of a malformed file; the delimiter is then
    taken from the header line, so that the wrong rows can be detected and
    reported instead of being read as a single column.

    Args:
        text: The decoded file text.

    Returns:
        The detected dialect. A file with no candidate delimiter in its
        header is read as a single comma-separated column.
    """
    sample = "\n".join(text.split("\n")[:_SNIFF_LINES])
    try:
        return csv.Sniffer().sniff(sample, delimiters=_CANDIDATE_DELIMITERS)
    except csv.Error:
        pass

    header_line = next((line for line in text.split("\n") if line.strip()), "")
    counts = {char: header_line.count(char) for char in _CANDIDATE_DELIMITERS}
    delimiter = max(counts, key=lambda char: counts[char])
    if counts[delimiter] == 0:
        return csv.excel

    class HeaderDialect(csv.excel):
        """Comma-separated dialect with the delimiter found in the header."""

    HeaderDialect.delimiter = delimiter
    return HeaderDialect


def _clean_header(row: list[str]) -> list[str]:
    """Clean header names, giving a name to empty columns.

    Args:
        row: The header row.

    Returns:
        The column names, stripped; empty names become ``column_N``.
    """
    return [cell.strip() or f"column_{number}" for number, cell in enumerate(row, start=1)]


def _row_to_text(header: list[str], row: list[str]) -> str:
    """Turn a data row into ``column: value; column: value`` text.

    Empty cells are left out to keep the text readable.

    Args:
        header: The column names.
        row: The data row, same length as the header.

    Returns:
        The row as a single line of text.
    """
    return "; ".join(
        f"{name}: {value.strip()}" for name, value in zip(header, row) if value.strip()
    )
