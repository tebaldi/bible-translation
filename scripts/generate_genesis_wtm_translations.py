from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Callable

from deep_translator import GoogleTranslator


REPO_ROOT = Path(__file__).resolve().parent.parent
WTM_DIR = REPO_ROOT / "sources" / "wtm" / "01_GEN"
ESV_DIR = REPO_ROOT / "sources" / "esv" / "01_GEN"
BHO_SOURCE_DIR = REPO_ROOT / "translations" / "bho" / "01_GEN"
BHO_OUTPUT_DIR = REPO_ROOT / "translations" / "bho" / "01_GEN"
PT_OUTPUT_DIR = REPO_ROOT / "translations" / "ptb" / "01_GEN"
CACHE_PATH = REPO_ROOT / "scripts" / ".genesis_wtm_mt_cache.json"

NUMBERED_LINE_PATTERN = re.compile(r"^(\d+)\s+(.*)$")
MARKDOWN_VERSE_PATTERN = re.compile(r"^\*\*(\d+)\*\*\s+(.*)$")
SPACE_PATTERN = re.compile(r"\s+")
FOOTNOTE_MARKER_PATTERN = re.compile(r"<N\d+>")
TRAILING_NOTE_PATTERN = re.compile(r"\s*\{.*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Genesis 1-25 from_wtm drafts for Bhojpuri and Brazilian Portuguese."
    )
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=25)
    parser.add_argument("--force", action="store_true", help="Overwrite existing outputs.")
    return parser.parse_args()


def clean_spaces(text: str) -> str:
    text = text.replace("\u00a0", " ")
    return SPACE_PATTERN.sub(" ", text).strip()


def strip_esv_notes(text: str) -> str:
    text = FOOTNOTE_MARKER_PATTERN.sub("", text)
    text = TRAILING_NOTE_PATTERN.sub("", text)
    return clean_spaces(text)


def parse_numbered_source(path: Path, cleaner: Callable[[str], str] | None = None) -> list[tuple[int, str]]:
    verses: list[tuple[int, str]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = NUMBERED_LINE_PATTERN.match(line)
        if match is None:
            raise ValueError(f"Malformed source line in {path}: {raw_line!r}")
        verse_num = int(match.group(1))
        text = match.group(2)
        if cleaner is not None:
            text = cleaner(text)
        verses.append((verse_num, text))
    return verses


def parse_markdown_chapter(path: Path) -> list[tuple[int, str]]:
    verses: list[tuple[int, str]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = MARKDOWN_VERSE_PATTERN.match(line)
        if match is None:
            raise ValueError(f"Malformed markdown verse line in {path}: {raw_line!r}")
        verses.append((int(match.group(1)), clean_spaces(match.group(2))))
    return verses


def verse_numbers(verses: list[tuple[int, str]]) -> list[int]:
    return [verse_num for verse_num, _ in verses]


def ensure_alignment(
    chapter: int,
    wtm_verses: list[tuple[int, str]],
    esv_verses: list[tuple[int, str]],
    bho_verses: list[tuple[int, str]],
) -> None:
    wtm_nums = verse_numbers(wtm_verses)
    esv_nums = verse_numbers(esv_verses)
    bho_nums = verse_numbers(bho_verses)
    if wtm_nums != esv_nums or wtm_nums != bho_nums:
        raise RuntimeError(
            f"Verse alignment mismatch in Genesis {chapter}: "
            f"wtm={wtm_nums} esv={esv_nums} bho={bho_nums}"
        )


def load_cache() -> dict[str, str]:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict[str, str]) -> None:
    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[idx : idx + size] for idx in range(0, len(items), size)]


def translate_batch_pt(texts: list[str], cache: dict[str, str]) -> list[str]:
    translator = GoogleTranslator(source="en", target="pt")
    results: list[str] = [""] * len(texts)

    pending: list[tuple[int, str]] = []
    for idx, text in enumerate(texts):
        key = f"pt::{text}"
        cached = cache.get(key)
        if cached is not None:
            results[idx] = cached
        else:
            pending.append((idx, text))

    for batch in chunked([item[1] for item in pending], 10):
        translated: list[str] | None = None
        for attempt in range(3):
            try:
                translated = translator.translate_batch(batch)
                break
            except Exception:
                time.sleep(1 + attempt)
        if translated is None:
            translated = []
            for text in batch:
                for attempt in range(3):
                    try:
                        translated.append(translator.translate(text))
                        break
                    except Exception:
                        time.sleep(1 + attempt)
                else:
                    raise RuntimeError(f"Portuguese translation failed for: {text}")

        for src, out in zip(batch, translated, strict=True):
            cache[f"pt::{src}"] = out

    for idx, text in enumerate(texts):
        results[idx] = cache[f"pt::{text}"]

    return results


def normalize_pt(text: str, source_text: str) -> str:
    text = clean_spaces(text)
    text = text.replace("\u200b", "").replace("\ufeff", "")
    text = text.replace("“", "\"").replace("”", "\"").replace("’", "'").replace("‘", "'")
    text = text.replace(" ,", ",").replace(" .", ".").replace(" ;", ";").replace(" :", ":")
    text = re.sub(r"\s+([?!])", r"\1", text)

    if "LORD" in source_text:
        text = re.sub(r"\bSenhor\b", "SENHOR", text)

    if text.count("\"") == 1:
        text = text.replace("\"", "")

    return text.strip()


def render_markdown(verses: list[tuple[int, str]]) -> str:
    return "\n\n".join(f"**{verse_num}** {text}" for verse_num, text in verses) + "\n"


def main() -> None:
    args = parse_args()

    BHO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cache = load_cache()

    for chapter in range(args.start, args.end + 1):
        wtm_verses = parse_numbered_source(WTM_DIR / f"CHAPTER_{chapter}.txt")
        esv_verses = parse_numbered_source(
            ESV_DIR / f"CHAPTER_{chapter}.txt",
            cleaner=strip_esv_notes,
        )
        bho_existing = parse_markdown_chapter(BHO_SOURCE_DIR / f"CHAPTER_{chapter}.from_esv.md")

        ensure_alignment(chapter, wtm_verses, esv_verses, bho_existing)

        bho_output_path = BHO_OUTPUT_DIR / f"CHAPTER_{chapter}.from_wtm.md"
        if args.force or not bho_output_path.exists():
            bho_output_path.write_text(render_markdown(bho_existing), encoding="utf-8")

        pt_output_path = PT_OUTPUT_DIR / f"CHAPTER_{chapter}.from_wtm.md"
        if args.force or not pt_output_path.exists():
            pt_translated = translate_batch_pt([text for _, text in esv_verses], cache)
            pt_verses = [
                (verse_num, normalize_pt(translated, source_text))
                for (verse_num, source_text), translated in zip(esv_verses, pt_translated, strict=True)
            ]
            pt_output_path.write_text(render_markdown(pt_verses), encoding="utf-8")

        save_cache(cache)


if __name__ == "__main__":
    main()
