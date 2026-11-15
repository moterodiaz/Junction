"""In-memory per-book session store (PRD section 2, section 4 step 3, section 6).

Keeps a session per book:
- Book metadata (title, author, location)
- Position in the text
- History of earlier questions and answers (text only, in memory)
The tenth question must be able to use the first nine.
Frames, audio, and images are never stored in the session.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class BookInfo:
    title: str = "Hamlet"
    author: str = "William Shakespeare"
    location: str = "Act 1, Scene 1"

    def to_dict(self) -> dict[str, str]:
        return {
            "title": self.title,
            "author": self.author,
            "location": self.location,
        }


@dataclass
class QAExchange:
    question: str
    answer: str
    passage: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "passage": self.passage,
            "timestamp": self.timestamp,
        }


class BookSession:
    """A reading session for a single book held strictly in memory."""

    candidate_books: List[BookInfo] = field(default_factory=lambda: [BookInfo()])
    max_position: Optional[Tuple[int, int, int]] = None
    seen_passages: List[str] = field(default_factory=list)

    def __init__(
        self,
        session_id: str,
        book: Optional[BookInfo] = None,
        candidate_books: Optional[List[BookInfo]] = None,
        max_position: Optional[Tuple[int, int, int]] = None,
        seen_passages: Optional[List[str]] = None,
    ) -> None:
        self.session_id = str(session_id)
        self.book = book or BookInfo()
        self.is_default_book: bool = (book is None)
        if candidate_books is not None:
            self.candidate_books = list(candidate_books)
        elif book is not None:
            self.candidate_books = [self.book]
        else:
            self.candidate_books = [self.book]
        self.history: List[QAExchange] = []
        self.awaiting_book_clarification: bool = False
        self.created_at = time.time()
        self.max_position = max_position
        self.seen_passages = list(seen_passages) if seen_passages is not None else []
        self._horizon_by_book: Dict[str, Tuple[Optional[Tuple[int, int, int]], List[str]]] = {}
        active_key = self._book_key(self.book.title)
        if active_key:
            self._horizon_by_book[active_key] = (self.max_position, list(self.seen_passages))

    @staticmethod
    def _book_key(title: Optional[str]) -> str:
        return (title or "").strip().lower()

    def record_seen_passage(
        self,
        passage_text: str,
        act: Optional[int] = None,
        scene: Optional[int] = None,
        line: Optional[int] = None,
    ) -> None:
        """Record visible passage text (deduping consecutive duplicates) and advance reading horizon."""
        if passage_text is not None and not isinstance(passage_text, str):
            raise TypeError("Session seen_passages must be text only (string)")

        cleaned = (passage_text or "").strip()
        if cleaned:
            if not self.seen_passages or self.seen_passages[-1] != cleaned:
                self.seen_passages.append(cleaned)

        if act is not None and scene is not None:
            try:
                line_val = int(line or 0)
                pos = (int(act), int(scene), line_val)
                if self.max_position is None or pos > self.max_position:
                    self.max_position = pos
            except (ValueError, TypeError):
                pass

        active_key = self._book_key(self.book.title) if self.book else ""
        if active_key:
            self._horizon_by_book[active_key] = (self.max_position, list(self.seen_passages))

    def get_reading_horizon_summary(self) -> str:
        """Return verified furthest reading position without trusting ungrounded book locations."""
        if self.max_position is not None:
            act, scene, line = self.max_position
            if line:
                return f"Act {act}, Scene {scene}, line {line}"
            return f"Act {act}, Scene {scene}"
        if self.seen_passages:
            return f"Observed {len(self.seen_passages)} unverified passage(s); exact book position unknown"
        return ""

    def add_candidate_book(self, book: BookInfo) -> None:
        """Add or update candidate book in the session, deduping by normalized title."""
        if not isinstance(book, BookInfo):
            raise TypeError("book must be a BookInfo instance")
        norm = book.title.strip().lower()
        for idx, existing in enumerate(self.candidate_books):
            if existing.title.strip().lower() == norm:
                self.candidate_books[idx] = book
                if self.book.title.strip().lower() == norm:
                    self.book = book
                return
        self.candidate_books.append(book)

    def set_active_book(self, title: str, author: str = "", location: str = "") -> None:
        """Update self.book, keep per-book horizon state isolated, and track in candidate_books."""
        self.is_default_book = False
        old_key = self._book_key(self.book.title) if self.book else ""
        norm = self._book_key(title)
        if old_key and old_key != norm:
            self._horizon_by_book[old_key] = (self.max_position, list(self.seen_passages))

        matched: Optional[BookInfo] = None
        for b in self.candidate_books:
            if self._book_key(b.title) == norm:
                matched = b
                break
        if matched is not None:
            if author:
                matched.author = author
            if location:
                matched.location = location
            self.book = matched
        else:
            new_book = BookInfo(title=title, author=author, location=location)
            self.book = new_book
            self.candidate_books.append(new_book)

        if old_key != norm:
            saved_pos, saved_passages = self._horizon_by_book.get(norm, (None, []))
            self.max_position = saved_pos
            self.seen_passages = list(saved_passages)
            if norm:
                self._horizon_by_book[norm] = (self.max_position, list(self.seen_passages))

    def add_exchange(
        self,
        question: str,
        answer: str,
        passage: str = "",
    ) -> QAExchange:
        """Record a question, answer summary, and optional passage text (text only)."""
        if not isinstance(question, str) or not isinstance(answer, str):
            raise TypeError("Session history must be text only (strings)")
        if passage is not None and not isinstance(passage, str):
            raise TypeError("Session passage must be text only (string)")

        exchange = QAExchange(
            question=question.strip(),
            answer=answer.strip(),
            passage=(passage or "").strip(),
        )
        self.history.append(exchange)
        return exchange

    def update_location(self, location: str) -> None:
        """Update current position in the book (e.g. 'Act 3, Scene 1')."""
        if location and isinstance(location, str) and location.strip():
            self.book.location = location.strip()

    def get_history(self, limit: Optional[int] = None) -> List[QAExchange]:
        """Return history up to limit (most recent last)."""
        if limit is None or limit <= 0:
            return list(self.history)
        return list(self.history[-limit:])

    def format_history_for_prompt(self, limit: Optional[int] = None) -> str:
        """Format prior Q&A exchanges as plain text for context injection."""
        exchanges = self.get_history(limit)
        if not exchanges:
            return ""
        lines: List[str] = []
        for i, ex in enumerate(exchanges, 1):
            lines.append(f"Q{i}: {ex.question}")
            lines.append(f"A{i}: {ex.answer}")
        return "\n".join(lines)

    def get_gemini_turns(self, limit: Optional[int] = None) -> List[dict[str, Any]]:
        """Return history as Gemini multi-turn conversation objects."""
        exchanges = self.get_history(limit)
        turns: List[dict[str, Any]] = []
        for ex in exchanges:
            user_text = f"Question: {ex.question}"
            if ex.passage:
                user_text = f"Passage: {ex.passage}\n{user_text}"
            turns.append({"role": "user", "parts": [{"text": user_text}]})
            turns.append({"role": "model", "parts": [{"text": ex.answer}]})
        return turns

    def clear_history(self) -> None:
        self.history.clear()


class SessionStore:
    """In-memory store for active BookSessions."""

    def __init__(self) -> None:
        self._sessions: Dict[str, BookSession] = {}

    def get_or_create(
        self,
        session_id: str,
        default_book: Optional[BookInfo] = None,
    ) -> BookSession:
        if session_id not in self._sessions:
            self._sessions[session_id] = BookSession(
                session_id=session_id,
                book=default_book,
            )
        return self._sessions[session_id]

    def get(self, session_id: str) -> Optional[BookSession]:
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def clear(self) -> None:
        self._sessions.clear()

    def __len__(self) -> int:
        return len(self._sessions)


# Global default in-memory session store
default_session_store = SessionStore()
