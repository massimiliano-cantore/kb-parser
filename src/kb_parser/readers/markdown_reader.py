"""Reader for Markdown (.md) files."""

import re
from pathlib import Path

from kb_parser.readers.base import BaseReader

_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n(?:---|\.\.\.)\n", re.DOTALL)
_FRONT_MATTER_TITLE = re.compile(r"^title:\s*['\"]?(.+?)['\"]?\s*$", re.MULTILINE)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_TITLE_HEADING = re.compile(r"^#[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)

# Line-level syntax, applied to each line.
_CODE_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^\s{0,3}#{1,6}[ \t]*(.*?)[ \t]*#*[ \t]*$")
_BLOCKQUOTE = re.compile(r"^\s*(>\s?)+")
_LIST_MARKER = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?")
_HORIZONTAL_RULE = re.compile(r"^\s*(?:[-*_=]\s*){3,}$")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$")
_LINK_DEFINITION = re.compile(r"^\s*\[[^\]]+\]:\s*\S+")

# Inline syntax, applied to the whole text.
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_REFERENCE_LINK = re.compile(r"\[([^\]]+)\]\[[^\]]*\]")
_AUTOLINK = re.compile(r"<((?:https?|mailto):[^>]+)>")
_HTML_TAG = re.compile(r"</?[A-Za-z][^>]*>")
_INLINE_CODE = re.compile(r"`+([^`]+)`+")
_BOLD = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
_STAR_ITALIC = re.compile(r"\*(?=\S)(.+?)(?<=\S)\*")
_UNDERSCORE_ITALIC = re.compile(r"(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)")
_STRIKETHROUGH = re.compile(r"~~(.+?)~~")


class MarkdownReader(BaseReader):
    """Reads Markdown files and strips the formatting syntax.

    The title is taken from the YAML front matter (``title:``) if present,
    otherwise from the first level-1 heading (``# Title``). The content is
    the text without Markdown symbols, so that searches and word counts are
    not affected by the formatting.
    """

    extensions = (".md", ".markdown")

    def parse(self, text: str, path: Path) -> tuple[str | None, str]:
        """Extract title and plain-text content from a Markdown file.

        Args:
            text: The decoded file text.
            path: The file being read.

        Returns:
            The title (or ``None``) and the content without Markdown syntax.
        """
        title = None
        front_matter = _FRONT_MATTER.match(text)
        if front_matter:
            title_match = _FRONT_MATTER_TITLE.search(front_matter.group(1))
            if title_match:
                title = title_match.group(1)
            text = text[front_matter.end():]

        text = _HTML_COMMENT.sub("", text)

        lines: list[str] = []
        in_code_block = False
        for line in text.split("\n"):
            if _CODE_FENCE.match(line):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                # Code is kept as is: it is searchable, but a "# comment"
                # inside a code block must not become the title.
                lines.append(line)
                continue
            if title is None:
                heading = _TITLE_HEADING.match(line)
                if heading:
                    title = _strip_inline(heading.group(1))
            stripped = _strip_line(line)
            if stripped is not None:
                lines.append(stripped)

        return title, _strip_inline("\n".join(lines))


def _strip_line(line: str) -> str | None:
    """Remove line-level Markdown syntax.

    Args:
        line: A single line of the document, outside code blocks.

    Returns:
        The line without block markers, or ``None`` if the line carries
        no text (rules, table separators, link definitions).
    """
    if (
        _HORIZONTAL_RULE.match(line)
        or _TABLE_SEPARATOR.match(line)
        or _LINK_DEFINITION.match(line)
    ):
        return None
    heading = _HEADING.match(line)
    if heading:
        return heading.group(1)
    line = _BLOCKQUOTE.sub("", line)
    line = _LIST_MARKER.sub("", line)
    if "|" in line:
        line = " ".join(cell.strip() for cell in line.strip().strip("|").split("|"))
    return line


def _strip_inline(text: str) -> str:
    """Remove inline Markdown syntax, keeping the visible text.

    Args:
        text: The text to clean.

    Returns:
        The text without links, images, emphasis, code marks and HTML tags.
    """
    text = _IMAGE.sub(r"\1", text)
    text = _LINK.sub(r"\1", text)
    text = _REFERENCE_LINK.sub(r"\1", text)
    text = _AUTOLINK.sub(r"\1", text)
    text = _HTML_TAG.sub("", text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _BOLD.sub(r"\2", text)
    text = _STAR_ITALIC.sub(r"\1", text)
    text = _UNDERSCORE_ITALIC.sub(r"\1", text)
    text = _STRIKETHROUGH.sub(r"\1", text)
    return text
