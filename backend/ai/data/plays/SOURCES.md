# Source Texts and Licences

This directory contains public-domain reference texts for plays used by MetaLab's literature reading companion (PRD section 2, section 8, and section 10 open question 7 / C4).

## Hamlet

- **Title**: The Tragedy of Hamlet, Prince of Denmark
- **Author**: William Shakespeare
- **Source URL**: https://www.gutenberg.org/ebooks/1524 (Project Gutenberg eBook #1524)
- **Direct Text**: https://www.gutenberg.org/cache/epub/1524/pg1524.txt
- **Licence**: Public Domain in the United States and most jurisdictions. Project Gutenberg License allows copying, redistribution, and derivative works.
- **File**: `hamlet.json`

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
