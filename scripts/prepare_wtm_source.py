from __future__ import annotations

import argparse
import re
from pathlib import Path


LINE_PATTERN = re.compile(
    r"^(?P<book>[1-4]?[A-Za-z]{2,3})\s+(?P<chapter>\d+):(?P<verse>\d+)(?:\s+(?P<text>.*))?$"
)
MORPH_TAG_PATTERN = re.compile(r"\s*\+?\(@[^)]*\)")
SPACE_PATTERN = re.compile(r"\s+")

QERE_TOKEN = "}}"
KETIV_TOKEN = "--"
PARAGRAPH_OPEN_TOKEN = "p"
PARAGRAPH_CLOSED_TOKEN = "s"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a translator-facing WTM source by stripping morphology tags "
            "from sources/wtm_utf8.txt."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("sources/wtm_utf8.txt"),
        help="Normalized UTF-8 WTM input path.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("sources/wtm_plain.txt"),
        help="Cleaned verse-per-line output path.",
    )
    return parser.parse_args()


def clean_verse_text(text: str) -> str:
    text = MORPH_TAG_PATTERN.sub("", text)
    text = text.replace(QERE_TOKEN, "[QERE]")
    text = text.replace(KETIV_TOKEN, "[KETIV]")

    # Preserve paragraph breaks in a compact, translator-visible form.
    text = re.sub(rf"(?<!\S){PARAGRAPH_OPEN_TOKEN}(?!\S)", "{P}", text)
    text = re.sub(rf"(?<!\S){PARAGRAPH_CLOSED_TOKEN}(?!\S)", "{S}", text)
    text = SPACE_PATTERN.sub(" ", text).strip()
    return text


def transform_line(raw_line: str, lineno: int, input_path: Path) -> str:
    line = raw_line.rstrip()
    match = LINE_PATTERN.match(line)
    if match is None:
        raise ValueError(f"Malformed line at {input_path}:{lineno}: {raw_line!r}")

    text = clean_verse_text(match.group("text") or "")
    location = f"{match.group('book')} {match.group('chapter')}:{match.group('verse')}"
    if text:
        return f"{location}  {text}"
    return location


def main() -> None:
    args = parse_args()
    lines: list[str] = []

    for lineno, raw_line in enumerate(args.input.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        lines.append(transform_line(raw_line, lineno, args.input))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[wtm_plain] wrote {len(lines)} verses to {args.output.as_posix()}")


if __name__ == "__main__":
    main()
