from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://media.ipsapps.org/b4child/osa/bho/"
BOOKS_JS_URL = urljoin(BASE_URL, "js/book-names.js")
OUTPUT_ROOT = Path("sources/bho")
BOOK_METADATA = {
    "01-WHENGODMADEEVERYTHING-001.html": {
        "slug": "01-when-god-made-everything",
        "title": "जब ईश्वर सबकुछ बनवलन",
    },
    "02-THESTARTOFMANSSADNESS-001.html": {
        "slug": "02-the-start-of-mans-sadness",
        "title": "मानव के दुःख के शुरुआत",
    },
    "03-NOAHANDTHEGREATFLOOD-001.html": {
        "slug": "03-noah-and-the-great-flood",
        "title": "नूह आ महा जलप्रलय",
    },
    "04-THEBIRTHOFJESUS-001.html": {
        "slug": "04-the-birth-of-jesus",
        "title": "यीशु के जनम",
    },
    "05-THEMIRACLESOFJESUS-001.html": {
        "slug": "05-the-miracles-of-jesus",
        "title": "यीशु के चमत्कार",
    },
    "06-THEFIRSTEASTER-001.html": {
        "slug": "06-the-first-easter",
        "title": "पहिला ईस्टर",
    },
    "07-HEAVENGODSBEAUTIFULHOME-001.html": {
        "slug": "07-heaven-gods-beautiful-home",
        "title": "स्वर्ग, परमेश्वर के सुन्दर घर",
    },
}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def fetch_text(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def fetch_binary(session: requests.Session, url: str) -> bytes:
    response = session.get(url, timeout=60)
    response.raise_for_status()
    return response.content


def parse_books(js_source: str) -> list[dict[str, str]]:
    matches = re.findall(r'\{ name: "([^"]+)", ref: "([^"]+)" \}', js_source)
    books: list[dict[str, str]] = []
    for display_name, ref in matches:
        stem = Path(ref).stem
        parts = stem.split("-", 2)
        order = parts[0]
        title = parts[1] if len(parts) > 1 else stem
        metadata = BOOK_METADATA.get(ref, {})
        books.append(
            {
                "display_name": display_name,
                "ref": ref,
                "order": order,
                "title": metadata.get("title", title),
                "slug": metadata.get("slug", f"{order}-{slugify(title)}"),
            }
        )
    return books


def parse_page(html: str, page_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    image = soup.select_one("#content img")
    if image is None or not image.get("src"):
        raise RuntimeError(f"Could not find content image in {page_url}")

    page_counter = soup.select_one("#content .p")
    next_chapter = soup.select_one("a[title='Next Chapter']")
    next_book = soup.select_one("a[title='Next Book']")

    return {
        "page_url": page_url,
        "image_url": urljoin(page_url, image["src"]),
        "page_counter": page_counter.get_text(strip=True) if page_counter else None,
        "next_page_url": urljoin(page_url, next_chapter["href"]) if next_chapter and next_chapter.get("href") else None,
        "next_book_url": urljoin(page_url, next_book["href"]) if next_book and next_book.get("href") else None,
    }


def download_book(session: requests.Session, book: dict[str, str]) -> None:
    story_dir = OUTPUT_ROOT / book["slug"]
    images_dir = story_dir / "images"
    pages: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    current_url = urljoin(BASE_URL, book["ref"])
    while current_url and current_url not in seen_urls:
        seen_urls.add(current_url)
        html = fetch_text(session, current_url)
        page = parse_page(html, current_url)

        image_name = Path(page["image_url"]).name
        image_path = images_dir / image_name
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(fetch_binary(session, page["image_url"]))

        page["local_image_path"] = image_path.as_posix()
        pages.append(page)

        counter = page.get("page_counter") or ""
        if counter:
            current_page, _, total_pages = counter.partition("/")
            if current_page and total_pages and current_page == total_pages:
                break

        if not page.get("next_page_url"):
            break
        current_url = page["next_page_url"]

    story_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "display_name": book["display_name"],
        "ref": book["ref"],
        "page_count": len(pages),
        "pages": pages,
    }
    (story_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    session = requests.Session()
    books_source = fetch_text(session, BOOKS_JS_URL)
    books = parse_books(books_source)

    (OUTPUT_ROOT / "catalog.json").write_text(
        json.dumps(books, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    for book in books:
        download_book(session, book)


if __name__ == "__main__":
    main()
