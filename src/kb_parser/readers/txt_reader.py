"""Reader for plain text (.txt) files."""

from pathlib import Path

from kb_parser.readers.base import BaseReader


class TxtReader(BaseReader):
    """Reads plain text files.

    The title is the first non-empty line; the content is the whole text.
    """

    extensions = (".txt",)

    def parse(self, text: str, path: Path) -> tuple[str | None, str]:
        """Extract title and content from a plain text file.

        Args:
            text: The decoded file text.
            path: The file being read.

        Returns:
            The first non-empty line as title and the full text as content.
        """
        title = next((line.strip() for line in text.split("\n") if line.strip()), None)
        return title, text
