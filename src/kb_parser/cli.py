"""Command line interface for kb_parser.

This is the only module that prints: it turns the user's commands into
calls to the scanner and the index, and their results into text.

Examples:
    python -m kb_parser build sample_archive --output index.json
    python -m kb_parser search "manutenzione"
    python -m kb_parser stats --top 3
"""

import argparse
import os
import sys
from pathlib import Path

from kb_parser import __version__
from kb_parser.document import Document
from kb_parser.exceptions import KBParserError
from kb_parser.index import DEFAULT_TOP, SORT_KEYS, KnowledgeBaseIndex
from kb_parser.scanner import ArchiveScanner

DEFAULT_INDEX = "index.json"
TITLE_WIDTH = 45
PATH_WIDTH = 50

EXIT_OK = 0
EXIT_ERROR = 1


def main(argv: list[str] | None = None) -> int:
    """Run the command line interface.

    Args:
        argv: Command line arguments. Defaults to ``sys.argv[1:]``.

    Returns:
        The process exit code: 0 on success, 1 on error (2 for invalid
        arguments, set by ``argparse``).
    """
    _make_output_safe()
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (KBParserError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return EXIT_ERROR
    except BrokenPipeError:
        # The output was closed early (e.g. piped into "head"): not an error.
        # Redirect stdout so Python does not complain again while exiting.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser with all the subcommands.

    Returns:
        The configured parser.
    """
    parser = argparse.ArgumentParser(
        prog="kb_parser",
        description="Build and query a knowledge base index from a folder of documents.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    index_option = argparse.ArgumentParser(add_help=False)
    index_option.add_argument(
        "--index", type=Path, default=Path(DEFAULT_INDEX),
        help=f"index file (default: {DEFAULT_INDEX})",
    )

    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    build = commands.add_parser("build", help="scan an archive folder and save the index")
    build.add_argument("archive", type=Path, help="folder containing the documents")
    build.add_argument(
        "--output", type=Path, default=Path(DEFAULT_INDEX),
        help=f"index file to write (default: {DEFAULT_INDEX})",
    )
    build.set_defaults(handler=_command_build)

    list_parser = commands.add_parser("list", parents=[index_option], help="list the documents")
    list_parser.add_argument(
        "--sort", choices=SORT_KEYS, default="path", help="sort order (default: path)"
    )
    list_parser.set_defaults(handler=_command_list)

    search = commands.add_parser(
        "search", parents=[index_option], help="search a keyword in titles and contents"
    )
    search.add_argument("keyword", help="text to look for (case-insensitive, also part of words)")
    search.set_defaults(handler=_command_search)

    filter_parser = commands.add_parser(
        "filter", parents=[index_option], help="list the documents of one format"
    )
    filter_parser.add_argument("format", help="file format, e.g. txt, md, csv")
    filter_parser.set_defaults(handler=_command_filter)

    stats = commands.add_parser("stats", parents=[index_option], help="show summary statistics")
    stats.add_argument(
        "--top", type=int, default=DEFAULT_TOP,
        help=f"number of longest documents to show (default: {DEFAULT_TOP})",
    )
    stats.set_defaults(handler=_command_stats)

    show = commands.add_parser("show", parents=[index_option], help="show a full document")
    show.add_argument("path", help="document path, as shown by the list command")
    show.set_defaults(handler=_command_show)

    return parser


def _command_build(args: argparse.Namespace) -> int:
    """Scan the archive, print the scan report and save the index.

    Args:
        args: Parsed arguments with ``archive`` and ``output``.

    Returns:
        The exit code.
    """
    documents, report = ArchiveScanner(args.archive).scan()
    index = KnowledgeBaseIndex.from_scan(documents, report)
    index.save(args.output)
    print(report.summary())
    print()
    print(f"Index saved to {args.output} ({_count(len(index), 'document')}).")
    return EXIT_OK


def _command_list(args: argparse.Namespace) -> int:
    """Print all the documents of the index.

    Args:
        args: Parsed arguments with ``index`` and ``sort``.

    Returns:
        The exit code.
    """
    index = KnowledgeBaseIndex.load(args.index)
    documents = index.list_documents(sort_by=args.sort)
    print(f"{_count(len(documents), 'document')} in {args.index}")
    print()
    _print_documents(documents)
    return EXIT_OK


def _command_search(args: argparse.Namespace) -> int:
    """Print the documents containing a keyword, most relevant first.

    Args:
        args: Parsed arguments with ``index`` and ``keyword``.

    Returns:
        The exit code.
    """
    index = KnowledgeBaseIndex.load(args.index)
    results = index.search(args.keyword)
    if not results:
        print(f"No documents contain '{args.keyword}'.")
        return EXIT_OK

    verb = "contains" if len(results) == 1 else "contain"
    print(f"{_count(len(results), 'document')} {verb} '{args.keyword}':")
    for position, result in enumerate(results, start=1):
        where = []
        if result.in_title:
            where.append("in title")
        if result.occurrences:
            where.append(f"{result.occurrences} in content")
        print()
        print(f"{position}. {result.document.title}")
        print(f"   {result.document.path}  ({', '.join(where)})")
        print(f"   {result.snippet}")
    return EXIT_OK


def _command_filter(args: argparse.Namespace) -> int:
    """Print the documents of one format.

    Args:
        args: Parsed arguments with ``index`` and ``format``.

    Returns:
        The exit code.
    """
    index = KnowledgeBaseIndex.load(args.index)
    documents = index.filter_by_format(args.format)
    if not documents:
        print(
            f"No documents with format '{args.format}'. "
            f"Formats in the index: {', '.join(index.formats()) or 'none'}."
        )
        return EXIT_OK
    print(f"{_count(len(documents), 'document')} with format '{documents[0].file_format}'")
    print()
    _print_documents(documents)
    return EXIT_OK


def _command_stats(args: argparse.Namespace) -> int:
    """Print the summary statistics of the index.

    Args:
        args: Parsed arguments with ``index`` and ``top``.

    Returns:
        The exit code.
    """
    index = KnowledgeBaseIndex.load(args.index)
    stats = index.statistics(top=args.top)

    print(f"Index: {args.index}")
    print(f"Built from: {index.source_folder or 'unknown'} on {index.created_at}")
    print()
    print(f"Documents:        {stats.document_count}")
    print(f"Total words:      {stats.total_words}")
    print(f"Average words:    {stats.average_words:.0f}")
    print(f"With a date:      {stats.with_date}")
    print(f"Without a date:   {stats.without_date}")
    if stats.oldest_date:
        print(f"Date range:       {stats.oldest_date} - {stats.newest_date}")

    print()
    print("Documents by format:")
    for file_format, count in stats.documents_by_format.items():
        print(f"  {file_format:10} {count}")

    print()
    print(f"Longest documents (top {len(stats.longest)}):")
    for document in stats.longest:
        print(f"  {document.word_count:>8} words  {document.path}")

    print()
    print(f"Files skipped at build time: {stats.skipped_count}")
    for reason, count in stats.skipped_by_reason.items():
        print(f"  - {reason}: {count}")
    return EXIT_OK


def _command_show(args: argparse.Namespace) -> int:
    """Print the full card of one document.

    Args:
        args: Parsed arguments with ``index`` and ``path``.

    Returns:
        The exit code.
    """
    index = KnowledgeBaseIndex.load(args.index)
    document = index.get(args.path)
    if document is None:
        print(
            f"Error: no document with path '{args.path}'. "
            "Use the list command to see the available paths.",
            file=sys.stderr,
        )
        return EXIT_ERROR

    print(f"Title:   {document.title}")
    print(f"Path:    {document.path}")
    print(f"Format:  {document.file_format}")
    print(f"Date:    {document.date or '-'}")
    print(f"Words:   {document.word_count}")
    print(f"Excerpt: {document.excerpt}")
    print()
    print(document.content)
    return EXIT_OK


def _print_documents(documents: list[Document]) -> None:
    """Print documents as an aligned table.

    Args:
        documents: The documents to print.
    """
    print(f"{'PATH':{PATH_WIDTH}}  {'FORMAT':6}  {'DATE':10}  {'WORDS':>7}  TITLE")
    for document in documents:
        print(
            f"{_shorten(document.path, PATH_WIDTH):{PATH_WIDTH}}  "
            f"{document.file_format:6}  {document.date or '-':10}  "
            f"{document.word_count:>7}  {_shorten(document.title, TITLE_WIDTH)}"
        )


def _count(number: int, noun: str) -> str:
    """Format a count with the noun in singular or plural form.

    Args:
        number: The count.
        noun: The singular noun.

    Returns:
        For example ``"1 document"`` or ``"3 documents"``.
    """
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _shorten(text: str, width: int) -> str:
    """Shorten a text to a maximum width, adding an ellipsis.

    Args:
        text: The text to shorten.
        width: The maximum number of characters.

    Returns:
        The text, cut and ending with ``…`` if it was too long.
    """
    return text if len(text) <= width else text[: width - 1] + "…"


def _make_output_safe() -> None:
    """Prevent crashes when the console cannot display some characters.

    Some consoles (for example the Windows one) use an encoding without
    emoji or non-Latin alphabets; printing them would raise
    ``UnicodeEncodeError``. Unsupported characters are replaced instead.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
