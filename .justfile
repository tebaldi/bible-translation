help:
  @just --list

split:
  python scripts/split_bible_sources.py

split-esv:
  python scripts/split_bible_sources.py esv

split-bgt:
  python scripts/split_bible_sources.py bgt

rebuild:
  python scripts/split_bible_sources.py --clean

rebuild-esv:
  python scripts/split_bible_sources.py --clean esv

rebuild-bgt:
  python scripts/split_bible_sources.py --clean bgt
