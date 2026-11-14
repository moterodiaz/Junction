"""Fixed L0 command words (PRD section 5): explain, draw, who is this."""

from __future__ import annotations

import re
from typing import Literal, Optional

Command = Literal["explain", "draw", "who_is_this"]

# Each pattern matches whole words, anywhere in the utterance ("can you draw this?").
# With only three commands, any "who" word means "who is this": Whisper writes it as
# "Whose this?", "Who is it?", "Who's in this picture?", "Tell me who this is."
# The cost is false hits such as "whose book is this", acceptable for L0.
# Word forms count too ("Drawing.", "Explanation"), still as whole words ("drawer", "withdraw" don't).
PATTERNS: dict[Command, re.Pattern[str]] = {
    "explain": re.compile(r"\bexpla(?:in(?:s|ed|ing)?|nations?)\b"),
    "draw": re.compile(r"\bdraw(?:s|n|ing)?\b"),
    "who_is_this": re.compile(r"\bwho(?:se|'s|s)?\b"),
}


def match_command(transcript: str) -> Optional[Command]:
    """Return the command that appears first in the transcript, or None."""
    text = transcript.lower().replace("’", "'")
    hits = [(m.start(), cmd) for cmd, pattern in PATTERNS.items() if (m := pattern.search(text))]
    return min(hits)[1] if hits else None
