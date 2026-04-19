from __future__ import annotations

import argparse
import html
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from deep_translator import GoogleTranslator


REPO_ROOT = Path(__file__).resolve().parent.parent
ESV_DIR = REPO_ROOT / "sources" / "esv" / "01_GEN"
BGT_DIR = REPO_ROOT / "sources" / "bgt" / "01_GEN"
OUTPUT_DIR = REPO_ROOT / "translations" / "bho" / "01_GEN"
CACHE_PATH = REPO_ROOT / "scripts" / ".genesis_bho_mt_cache.json"
BRENTON_URL_TEMPLATE = "https://ebible.org/englxxup/GEN{chapter:02d}.htm"


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


def clean_spaces(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_esv_chapter(chapter: int) -> list[tuple[int, str]]:
    path = ESV_DIR / f"CHAPTER_{chapter}.txt"
    verses: list[tuple[int, str]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^(\d+)\s+(.*)$", line)
        if not match:
            continue
        verse_num = int(match.group(1))
        text = match.group(2)
        text = re.sub(r"<N\d+>", "", text)
        text = re.sub(r"\s*\{.*$", "", text)
        text = clean_spaces(text)
        verses.append((verse_num, text))
    return verses


def parse_bgt_chapter(chapter: int) -> list[tuple[int, str]]:
    path = BGT_DIR / f"CHAPTER_{chapter}.txt"
    verses: list[tuple[int, str]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^(\d+)\s+(.*)$", line)
        if not match:
            continue
        verse_num = int(match.group(1))
        text = clean_spaces(match.group(2))
        verses.append((verse_num, text))
    return verses


def parse_brenton_chapter(chapter: int, session: requests.Session) -> list[tuple[int, str]]:
    response = session.get(BRENTON_URL_TEMPLATE.format(chapter=chapter), timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    main = soup.select_one("div.main")
    if main is None:
        raise RuntimeError(f"Could not find main Brenton text for Genesis {chapter}")

    verses: list[tuple[int, str]] = []
    for span in main.select("span.verse"):
        verse_num = int(clean_spaces(span.get_text(" ", strip=True)))
        parts: list[str] = []
        for sibling in span.next_siblings:
            if isinstance(sibling, Tag) and sibling.name == "span" and "verse" in (sibling.get("class") or []):
                break
            if isinstance(sibling, NavigableString):
                parts.append(str(sibling))
            elif isinstance(sibling, Tag):
                parts.append(sibling.get_text(" ", strip=True))

        text = html.unescape(" ".join(parts))
        text = re.sub(r"\[[^\]]+\]", "", text)
        text = clean_spaces(text)
        if text:
            verses.append((verse_num, text))

    return verses


def load_bgt_bridge_chapter(
    chapter: int,
    session: requests.Session,
) -> list[tuple[int, str]]:
    local_bgt = parse_bgt_chapter(chapter)
    brenton = parse_brenton_chapter(chapter, session)

    local_nums = [verse_num for verse_num, _ in local_bgt]
    brenton_nums = [verse_num for verse_num, _ in brenton]
    if local_nums != brenton_nums:
        raise RuntimeError(
            f"BGT/Brenton verse mismatch in Genesis {chapter}: "
            f"local={local_nums} brenton={brenton_nums}"
        )

    # Use repository BGT for alignment/provenance and Brenton English only as
    # an MT bridge because the local BGT text is transliterated Greek.
    return [(verse_num, bridge_text) for (verse_num, _), (_, bridge_text) in zip(local_bgt, brenton, strict=True)]


def normalize_bho(text: str, track: str, source_text: str) -> str:
    text = clean_spaces(text)
    text = text.replace("\u200b", "").replace("\ufeff", "")
    text = text.replace("“", "\"").replace("”", "\"").replace("‘", "'").replace("’", "'")

    replacements = [
        ("भगवान", "परमेश्वर"),
        ("परमेस् वर", "परमेश्वर"),
        ("परमेस्वर", "परमेश्वर"),
        ("परमे वर", "परमेश्वर"),
        ("बगइचा", "बगीचा"),
        ("बागीचा", "बगीचा"),
        ("बगीचा", "बगीचा"),
        ("आकाशवाणी", "आकाशमंडल"),
        ("आकाश के आकाश", "आकाशमंडल"),
        ("अनुग्रह", "कृपा"),
        ("आऊर", "आ"),
        ("अउरी", "आ"),
        ("अवुरी", "आ"),
        ("काहेकि", "काहे कि"),
        ("बाऊर", "बुरा"),
        ("अच्छाई-बाऊर", "अच्छाई-बुराई"),
        ("ईश्वर के नजर में कृपा मिलल", "ईश्वर के नजर में कृपा मिलल"),
        ("प्रभु के नजर में कृपा मिलल", "प्रभु के नजर में कृपा मिलल"),
        ("जिंदा", "जिअत"),
        ("बाबूजी", "बाप"),
        ("अबहीं", "अबहियों"),
        ("खेत के कवनो जानवर से भी जादा", "खेत के सभ जानवर से जियादा"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)

    if track == "esv":
        text = text.replace("परमेश्वर परमेश्वर", "यहोवा परमेश्वर")
        text = text.replace("प्रभु परमेश्वर", "यहोवा परमेश्वर")
        text = text.replace("प्रभु ", "यहोवा ")
        if "LORD God" in source_text:
            text = re.sub(r"^(तब|आ|और|फेर|फिर)?\s*परमेश्वर\b", lambda m: f"{m.group(1)} यहोवा परमेश्वर".strip() if m.group(1) else "यहोवा परमेश्वर", text, count=1)
            text = re.sub(r"^(तब|आ|और|फेर|फिर)?\s*यहोवा\b", lambda m: f"{m.group(1)} यहोवा परमेश्वर".strip() if m.group(1) else "यहोवा परमेश्वर", text, count=1)
    else:
        text = text.replace("परमेश्वर परमेश्वर", "प्रभु परमेश्वर")
        if "Lord God" in source_text:
            text = re.sub(r"^(तब|आ|और|फेर|फिर)?\s*परमेश्वर\b", lambda m: f"{m.group(1)} प्रभु परमेश्वर".strip() if m.group(1) else "प्रभु परमेश्वर", text, count=1)

    # Respectful divine speech reads better with "कहलन".
    if re.match(r"^(तब|आ|और|फेर|फिर)?\s*(यहोवा परमेश्वर|प्रभु परमेश्वर|परमेश्वर)\b", text):
        text = text.replace("कहलस", "कहलन", 1)
        text = text.replace("कहले", "कहलन", 1)

    text = text.replace("“", "\"").replace("”", "\"")
    text = text.strip()

    # Keep chapter-file lines plain; no unmatched leading/trailing quotes.
    if text.count("\"") == 1:
        text = text.replace("\"", "")

    return text


def translate_batch(texts: list[str], cache: dict[str, str]) -> list[str]:
    translator = GoogleTranslator(source="en", target="bho")
    results: list[str] = [""] * len(texts)

    pending: list[tuple[int, str]] = []
    for idx, text in enumerate(texts):
        key = f"bho::{text}"
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
                    raise RuntimeError(f"Translation failed for: {text}")

        for src, out in zip(batch, translated, strict=True):
            cache[f"bho::{src}"] = out

    for idx, text in enumerate(texts):
        results[idx] = cache[f"bho::{text}"]

    return results


def render_chapter(
    chapter: int,
    track: str,
    source_verses: list[tuple[int, str]],
    cache: dict[str, str],
) -> str:
    source_texts = [text for _, text in source_verses]
    translated_texts = translate_batch(source_texts, cache)
    lines: list[str] = []

    for (verse_num, source_text), translated in zip(source_verses, translated_texts, strict=True):
        normalized = normalize_bho(translated, track, source_text)
        lines.append(f"**{verse_num}** {normalized}")

    return "\n\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Bhojpuri Genesis chapter drafts.")
    parser.add_argument("--start", type=int, default=3)
    parser.add_argument("--end", type=int, default=50)
    parser.add_argument("--force", action="store_true", help="Overwrite existing chapter files.")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cache = load_cache()
    session = requests.Session()

    for chapter in range(args.start, args.end + 1):
        esv_out = OUTPUT_DIR / f"CHAPTER_{chapter}.from_esv.md"
        bgt_out = OUTPUT_DIR / f"CHAPTER_{chapter}.from_bgt.md"

        if args.force or not esv_out.exists():
            esv_source = parse_esv_chapter(chapter)
            esv_out.write_text(
                render_chapter(chapter, "esv", esv_source, cache),
                encoding="utf-8",
            )

        if args.force or not bgt_out.exists():
            bgt_source = load_bgt_bridge_chapter(chapter, session)
            bgt_out.write_text(
                render_chapter(chapter, "bgt", bgt_source, cache),
                encoding="utf-8",
            )

        save_cache(cache)


if __name__ == "__main__":
    main()
