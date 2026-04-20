from __future__ import annotations

import argparse
import re
import shutil
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path


LINE_PATTERN = re.compile(
    r"^(?P<book>[1-4]?[A-Za-z]{2,3})\s+(?P<chapter>\d+):(?P<verse>\d+)(?:\s+(?P<text>.*))?$"
)


@dataclass(frozen=True)
class SourceConfig:
    name: str
    input_path: Path
    output_path: Path
    encodings: tuple[str, ...]


@dataclass(frozen=True)
class ParsedLine:
    book: str
    chapter: int
    verse: int
    text: str


SOURCE_CONFIGS = {
    "esv": SourceConfig(
        name="esv",
        input_path=Path("sources/esv.txt"),
        output_path=Path("sources/esv"),
        encodings=("utf-8", "utf-8-sig"),
    ),
    "bgt": SourceConfig(
        name="bgt",
        input_path=Path("sources/bgt.txt"),
        output_path=Path("sources/bgt"),
        encodings=("cp1252", "latin-1"),
    ),
    "wtm": SourceConfig(
        name="wtm",
        input_path=Path("sources/wtm.txt"),
        output_path=Path("sources/wtm"),
        encodings=("utf-8", "utf-8-sig"),
    ),
    "wtm_utf8": SourceConfig(
        name="wtm_utf8",
        input_path=Path("sources/wtm_utf8.txt"),
        output_path=Path("sources/wtm_utf8"),
        encodings=("utf-8", "utf-8-sig"),
    ),
    "wtm_plain": SourceConfig(
        name="wtm_plain",
        input_path=Path("sources/wtm_plain.txt"),
        output_path=Path("sources/wtm_plain"),
        encodings=("utf-8", "utf-8-sig"),
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Split verse-per-line Bible source files into "
            "sources/{source}/{book_folder}/CHAPTER_{chapter}.txt"
        )
    )
    parser.add_argument(
        "sources",
        nargs="*",
        choices=["all", *SOURCE_CONFIGS],
        help="Which source(s) to split. Defaults to all.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete the generated output directory for each selected source before writing.",
    )
    return parser.parse_args()


def read_source_text(config: SourceConfig) -> str:
    last_error: Exception | None = None
    for encoding in config.encodings:
        try:
            return config.input_path.read_text(encoding=encoding)
        except UnicodeDecodeError as error:
            last_error = error
    raise RuntimeError(f"Could not decode {config.input_path} with {config.encodings}") from last_error


def parse_line(raw_line: str, lineno: int, input_path: Path) -> ParsedLine:
    line = raw_line.rstrip()
    match = LINE_PATTERN.match(line)
    if match is None:
        raise ValueError(f"Malformed line at {input_path}:{lineno}: {raw_line!r}")

    return ParsedLine(
        book=match.group("book"),
        chapter=int(match.group("chapter")),
        verse=int(match.group("verse")),
        text=match.group("text") or "",
    )


def parse_source(config: SourceConfig) -> OrderedDict[str, OrderedDict[int, list[ParsedLine]]]:
    books: OrderedDict[str, OrderedDict[int, list[ParsedLine]]] = OrderedDict()
    seen_locations: set[tuple[str, int, int]] = set()

    for lineno, raw_line in enumerate(read_source_text(config).splitlines(), start=1):
        if not raw_line.strip():
            continue

        parsed = parse_line(raw_line, lineno, config.input_path)
        location = (parsed.book, parsed.chapter, parsed.verse)
        if location in seen_locations:
            raise ValueError(f"Duplicate verse reference at {config.input_path}:{lineno}: {location}")
        seen_locations.add(location)

        chapters = books.setdefault(parsed.book, OrderedDict())
        verses = chapters.setdefault(parsed.chapter, [])
        if verses and parsed.verse <= verses[-1].verse:
            raise ValueError(
                "Verse ordering regression at "
                f"{config.input_path}:{lineno}: {parsed.book} {parsed.chapter}:{parsed.verse}"
            )
        verses.append(parsed)

    return books


def safe_remove_tree(path: Path, expected_parent: Path) -> None:
    resolved_path = path.resolve()
    resolved_parent = expected_parent.resolve()
    if resolved_path.parent != resolved_parent:
        raise RuntimeError(f"Refusing to delete unexpected path: {resolved_path}")
    if resolved_path.exists():
        shutil.rmtree(resolved_path)


def render_verse(parsed: ParsedLine) -> str:
    if parsed.text:
        return f"{parsed.verse} {parsed.text}"
    return str(parsed.verse)


def write_source(config: SourceConfig, books: OrderedDict[str, OrderedDict[int, list[ParsedLine]]], clean: bool) -> None:
    if clean:
        safe_remove_tree(config.output_path, config.output_path.parent)

    config.output_path.mkdir(parents=True, exist_ok=True)
    book_index_width = max(2, len(str(len(books))))

    for book_index, (book_code, chapters) in enumerate(books.items(), start=1):
        book_folder = f"{book_index:0{book_index_width}d}_{book_code.upper()}"
        book_path = config.output_path / book_folder
        book_path.mkdir(parents=True, exist_ok=True)

        for chapter_number, verses in chapters.items():
            chapter_path = book_path / f"CHAPTER_{chapter_number}.txt"
            content = "\n".join(render_verse(verse) for verse in verses) + "\n"
            chapter_path.write_text(content, encoding="utf-8")


def count_chapters(books: OrderedDict[str, OrderedDict[int, list[ParsedLine]]]) -> int:
    return sum(len(chapters) for chapters in books.values())


def count_verses(books: OrderedDict[str, OrderedDict[int, list[ParsedLine]]]) -> int:
    return sum(len(verses) for chapters in books.values() for verses in chapters.values())


def resolve_sources(raw_sources: list[str]) -> list[SourceConfig]:
    if not raw_sources or "all" in raw_sources:
        return [SOURCE_CONFIGS[name] for name in SOURCE_CONFIGS]
    return [SOURCE_CONFIGS[name] for name in raw_sources]


def main() -> None:
    args = parse_args()
    for config in resolve_sources(args.sources):
        books = parse_source(config)
        write_source(config, books, clean=args.clean)
        print(
            f"[{config.name}] wrote {len(books)} books, "
            f"{count_chapters(books)} chapters, {count_verses(books)} verses "
            f"to {config.output_path.as_posix()}"
        )


if __name__ == "__main__":
    main()
