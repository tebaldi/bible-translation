# AGENTS.md

## Purpose

This repository is a Bible translation workspace.

- The long-term goal is to translate the Bible into new languages.
- The current active target language is Bhojpuri (`bho`).
- Target countries for this language work are India, Mauritius, and Nepal.
- The current scope is the Old Testament first.
- Work interactively: produce one small, reviewable unit at a time instead of bulk-generating large portions of the corpus.

## Repository Structure

- `sources/` contains reference material and source texts. Treat it as immutable unless explicitly asked to regenerate, correct, or replace source data.
- `translations/` contains translation drafts and reviewed outputs. Treat it as the canonical destination for translation work.
- `scripts/download_bho_story.py` and `scripts/ocr_bho_stories.js` are source-ingestion helpers. They are not the primary output path for Bible translation deliverables.

## Translation Workflow

- Use reference texts under `sources/`, including `sources/esv.txt` and `sources/bgt.txt`, when preparing translations.
- Translate chapter by chapter.
- Produce separate output files for each source basis. Use the source file stem in the output filename, such as `from_esv` and `from_bgt`.
- Keep the workflow interactive: draft the requested chapter, surface uncertainties, and stop for review instead of continuing automatically into later chapters.

## Output Format

- Use this path pattern for chapter outputs: `translations/{language}/{book_folder}/CHAPTER_{chapter}.from_{source}.md`
- The current language folder is `translations/bho/`.
- Use zero-padded canonical order plus a short book code for book folders, for example `01_GEN`, `02_EXO`, `03_LEV`.
- Example output path: `translations/bho/01_GEN/CHAPTER_1.from_esv.md`
- `from_{source}` maps to the source filename stem in `sources/`, for example `esv` from `sources/esv.txt` and `bgt` from `sources/bgt.txt`.
- Write each chapter file as Markdown with verse-numbered lines inside the chapter file.
- Default Bhojpuri output to Devanagari script unless explicitly instructed otherwise.

## Quality Rules

- Preserve chapter and verse alignment with the source chapter being translated.
- Do not collapse verses into free prose.
- Do not mix multiple source bases into a single `from_{source}` file.
- When wording is uncertain, source text is missing, or OCR/reference quality is questionable, call it out explicitly instead of silently guessing.
- Avoid rewriting unrelated generated or downloaded assets under `sources/`.

## Working Defaults

- Prefer minimal, focused edits.
- Prefer consistency across files over stylistic variation.
- Do not rename established folder conventions without explicit instruction.
- When a needed book or chapter directory is missing, create only the specific target path required for the chapter being worked on.
