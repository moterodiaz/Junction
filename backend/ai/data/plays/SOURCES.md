# Source Texts and Licences

This directory contains public-domain reference texts for plays used by MetaLab's literature reading companion (PRD section 2, section 8, and section 10 open question 7 / C4).

## Hamlet

- **Title**: The Tragedy of Hamlet, Prince of Denmark
- **Author**: William Shakespeare
- **Source URL**: https://www.gutenberg.org/ebooks/1524 (Project Gutenberg eBook #1524)
- **Direct Text**: https://www.gutenberg.org/cache/epub/1524/pg1524.txt
- **Licence**: Public Domain in the United States and most jurisdictions. Project Gutenberg License allows copying, redistribution, and derivative works.
- **File**: `hamlet.json`

### Hamlet scene notes

- **File**: `hamlet_notes.json` (one entry per scene: summary, characters on stage, glossary, themes)
- **Origin**: hand-written study notes in original wording for this project. They are not copied from any copyrighted edition, commentary or study guide; glossary terms are words from the public-domain text above.
- **Use**: loaded next to `hamlet.json` by `source_loader.py` and added to the reasoning prompt when a page matches a passage. The backend never calls a model to produce notes.
- **Validation**: `python3 backend/ai/make_notes.py` checks that every scene in `hamlet.json` has an entry and every glossary term occurs in its scene. `--skeleton <play>` prints an empty notes file for a new play; a play without a notes file works as before.

## Adding a Play (Data-Only Change)

Per PRD Section 10 Open Question 7 (C4) and Issue #29:
> "Open question 7 (which other plays) stays open: make adding a play a data-only change."

Adding a new play requires **no code changes**. Simply add a `<play_id>.json` file to this directory (`backend/ai/data/plays/`) following the schema below. The loader (`backend/ai/source_loader.py`) will automatically discover it on startup or dynamically via `list_plays()`.

### Schema

```json
{
  "id": "play_id",
  "title": "Play Title (e.g. Macbeth)",
  "full_title": "The Full Title of the Play",
  "author": "William Shakespeare",
  "source_url": "https://www.gutenberg.org/ebooks/...",
  "license": "Public Domain (Project Gutenberg License)",
  "acts": [
    {
      "act": 1,
      "act_roman": "I",
      "scenes": [
        {
          "scene": 1,
          "scene_roman": "I",
          "location_desc": "An open place.",
          "lines": [
            {
              "type": "line",
              "line": 1,
              "speaker": "FIRST WITCH",
              "text": "When shall we three meet again"
            }
          ]
        }
      ]
    }
  ]
}
```
