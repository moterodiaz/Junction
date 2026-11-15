import time
import asyncio
import io
import json
import logging
import os
from pathlib import Path
import re
from typing import Any
import unittest
from unittest import mock
import urllib.error

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.main import app
import app.pipeline as pipeline
from ai.reasoning import (
    DEFAULT_MODEL_REASON,
    HttpGeminiClient,
    ReasoningError,
    StubGeminiClient,
    parse_reasoning_json,
    ground_passage,
    set_reasoning_client,
    think,
)
from ai.session import (
    BookInfo,
    BookSession,
    SessionStore,
    default_session_store,
)

SCHEMA = Draft202012Validator(
    json.loads(
        (Path(__file__).resolve().parents[2] / "contracts" / "ws-messages.schema.json").read_text()
    )
)
FRAME = {"mime": "image/jpeg", "b64": "/9j/4AAQSkZJRgABAQEASABIAAD/"}


class RealParserGeminiClient:
    """Client that passes a Gemini response payload to HttpGeminiClient._parse_gemini_response."""

    def __init__(self, raw_candidate_text: str):
        self.raw_candidate_text = raw_candidate_text

    async def generate_reasoning(
        self,
        command: str,
        page_text: str,
        session: BookSession,
        model: str = DEFAULT_MODEL_REASON,
        passage_match: Any = None,
        spoiler_guard: bool = False,
    ):
        raw_api_payload = json.dumps({
            "candidates": [{
                "content": {
                    "parts": [{"text": self.raw_candidate_text}]
                }
            }]
        })
        client = HttpGeminiClient(api_key="mock-gemini-key")
        return client._parse_gemini_response(raw_api_payload, session)


class BookSessionAndReasoningTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        default_session_store.clear()
        set_reasoning_client(None)

    def tearDown(self):
        default_session_store.clear()
        set_reasoning_client(None)

    async def test_think_returns_expected_card_contract(self):
        session_id = "test-session-1"
        command = "explain this passage"
        page_text = "To be, or not to be, that is the question..."

        answer = await think(command, page_text, session_id, client=StubGeminiClient())

        self.assertIn("title", answer)
        self.assertIn("caption", answer)
        self.assertIn("speech_text", answer)
        self.assertIn("image_prompt", answer)
        self.assertIn("book", answer)
        self.assertIn("sources", answer)

        self.assertIsInstance(answer["title"], str)
        self.assertIsInstance(answer["caption"], str)
        self.assertIsInstance(answer["speech_text"], str)
        self.assertIsInstance(answer["image_prompt"], str)
        self.assertIsInstance(answer["book"], dict)
        self.assertIsInstance(answer["sources"], list)

        self.assertEqual(answer["book"]["title"], "Hamlet")
        self.assertEqual(answer["book"]["author"], "William Shakespeare")
        self.assertTrue(len(answer["sources"]) > 0)
        self.assertTrue(answer["sources"][0]["url"].startswith("https://"))

    async def test_tenth_question_uses_first_nine(self):
        """PRD section 2 requirement: The answer to the tenth question uses the first nine."""
        session_id = "hamlet-reader-1"
        stub = StubGeminiClient()

        # Run 9 sequential questions and answers
        for i in range(1, 10):
            cmd = f"Question {i}: What is happening in this scene?"
            passage = f"Passage snippet {i} from Act 3 Scene 1."
            ans = await think(cmd, passage, session_id, client=stub)
            self.assertTrue(len(ans["caption"]) > 0)

        session = default_session_store.get(session_id)
        self.assertIsNotNone(session)
        self.assertEqual(len(session.history), 9)

        # Call #10: "Why is he angry at her now?"
        cmd_10 = "Question 10: Why is he angry at her now?"
        passage_10 = "Get thee to a nunnery: why wouldst thou be a breeder of sinners?"
        ans_10 = await think(cmd_10, passage_10, session_id, client=stub)

        # Check call records on stub client
        self.assertEqual(len(stub.calls), 10)
        tenth_call = stub.calls[9]
        self.assertEqual(tenth_call["command"], cmd_10)
        self.assertEqual(tenth_call["history_count"], 9)
        self.assertEqual(len(tenth_call["history_snapshot"]), 9)

        # Verify that all 9 prior questions are in the snapshot passed to the reasoning call
        for i in range(1, 10):
            self.assertEqual(
                tenth_call["history_snapshot"][i - 1]["question"],
                f"Question {i}: What is happening in this scene?",
            )

        # Verify session now has 10 exchanges
        self.assertEqual(len(session.history), 10)
        self.assertEqual(session.history[9].question, cmd_10)

        # Verify 10th answer explicitly builds on the prior questions
        self.assertIn("Question 10 builds on 9 prior questions", ans_10["caption"])
        self.assertIn("Building on our earlier discussion", ans_10["speech_text"])

    def test_session_store_crud_and_isolation(self):
        store = SessionStore()
        self.assertEqual(len(store), 0)

        s1 = store.get_or_create("s1", default_book=BookInfo(title="Macbeth", location="Act 1"))
        s2 = store.get_or_create("s2", default_book=BookInfo(title="Hamlet", location="Act 2"))

        self.assertEqual(len(store), 2)
        self.assertEqual(store.get("s1").book.title, "Macbeth")
        self.assertEqual(store.get("s2").book.title, "Hamlet")

        s1.add_exchange("Q1", "A1")
        self.assertEqual(len(s1.history), 1)
        self.assertEqual(len(s2.history), 0)

        self.assertTrue(store.delete("s1"))
        self.assertIsNone(store.get("s1"))
        self.assertEqual(len(store), 1)

        store.clear()
        self.assertEqual(len(store), 0)

    def test_session_text_only_validation(self):
        """PRD section 6: The book session holds text only."""
        session = BookSession("s-text")
        # Strings are allowed
        session.add_exchange("Question text", "Answer text", "Passage text")
        self.assertEqual(len(session.history), 1)

        # Non-string questions or answers are rejected
        with self.assertRaises(TypeError):
            session.add_exchange(12345, "Answer")  # type: ignore

        with self.assertRaises(TypeError):
            session.add_exchange("Question", {"key": "not a string"})  # type: ignore

        with self.assertRaises(TypeError):
            session.add_exchange("Question", "Answer", b"binary bytes")  # type: ignore

    def test_session_format_history_and_turns(self):
        session = BookSession("s-format")
        session.add_exchange("Who is Claudius?", "The King of Denmark and Hamlet's uncle.")
        session.add_exchange("Who is Gertrude?", "The Queen and Hamlet's mother.")

        formatted = session.format_history_for_prompt()
        self.assertIn("Q1: Who is Claudius?", formatted)
        self.assertIn("A1: The King of Denmark", formatted)
        self.assertIn("Q2: Who is Gertrude?", formatted)

        turns = session.get_gemini_turns()
        self.assertEqual(len(turns), 4)  # 2 user turns + 2 model turns
        self.assertEqual(turns[0]["role"], "user")
        self.assertEqual(turns[1]["role"], "model")

    def test_rayban_additive_display_prompt_styling(self):
        """Ray-Ban Display additive optical lens requires black background and luminous subject."""
        session = BookSession("s-rayban")
        raw_json = (
            '{"title": "Hamlet, Act 3, Scene 1", "caption": "Hamlet reflects.", '
            '"speech_text": "Spoken explanation.", '
            '"image_prompt": "Prince in a dimly lit chamber", '
            '"book": {"title": "Hamlet", "author": "William Shakespeare", "location": "Act 3, Scene 1"}}'
        )
        parsed = parse_reasoning_json(raw_json, session)
        self.assertIn("black background", parsed["image_prompt"].lower())
        self.assertIn("#000000", parsed["image_prompt"])

    def test_json_parsing_with_markdown_fences(self):
        session = BookSession("s-fence")
        fenced = (
            '```json\n'
            '{\n'
            '  "title": "Hamlet, Act 1, Scene 2",\n'
            '  "caption": "The court celebrates the new king.",\n'
            '  "speech_text": "Claudius addresses the court.",\n'
            '  "image_prompt": "Royals feasting in a grand hall, black background (#000000), dramatic light.",\n'
            '  "book": {"title": "Hamlet", "author": "William Shakespeare", "location": "Act 1, Scene 2"},\n'
            '  "sources": [{"title": "Hamlet", "url": "https://gutenberg.org"}]\n'
            '}\n'
            '```'
        )
        parsed = parse_reasoning_json(fenced, session)
        self.assertEqual(parsed["title"], "Hamlet, Act 1, Scene 2")
        self.assertEqual(parsed["book"]["location"], "Act 1, Scene 2")

    async def test_error_handling_when_gemini_fails(self):
        stub = StubGeminiClient(fail=True)
        with self.assertRaises(ReasoningError):
            await think("explain", "passage", "s-fail", client=stub)

    async def test_speech_text_saved_in_session_history(self):
        """Thread 2: speech_text (not caption) is recorded so follow-ups have full spoken context."""
        stub = StubGeminiClient(default_answer={
            "title": "Hamlet, Act 3, Scene 1",
            "caption": "A short caption.",
            "speech_text": "A richer spoken explanation with extra detail.",
            "image_prompt": "prompt, pure black background (#000000)",
            "book": {"title": "Hamlet", "author": "William Shakespeare", "location": "Act 3, Scene 1"},
            "sources": [],
        })
        await think("explain", "passage text", "s-speech-history", client=stub)
        session = default_session_store.get("s-speech-history")
        self.assertIsNotNone(session)
        self.assertEqual(len(session.history), 1)
        self.assertEqual(session.history[0].answer,
                         "A richer spoken explanation with extra detail.")
        self.assertNotEqual(session.history[0].answer, "A short caption.")

    def test_parse_reasoning_json_with_blank_whitespace_null_caption(self):
        """#175: blank, whitespace, or null caption falls back to usable speech_text."""
        session = BookSession("s-blank-caption")
        speech = "Hamlet wonders whether enduring his pain is nobler than dying."

        cases = [
            {"caption": ""},
            {"caption": "   \n\t  "},
            {"caption": None},
            {},
        ]

        for payload_override in cases:
            payload = {
                "title": "Hamlet, Act 3, Scene 1",
                "speech_text": speech,
                "book": {"title": "Hamlet", "author": "William Shakespeare", "location": "Act 3, Scene 1"},
                **payload_override,
            }
            parsed = parse_reasoning_json(json.dumps(payload), session)
            self.assertEqual(parsed["caption"], speech)
            self.assertEqual(parsed["speech_text"], speech)
            self.assertIn(f"Illustration of {speech}", parsed["image_prompt"])

    def test_parse_reasoning_json_with_blank_or_missing_speech_text(self):
        """#175: blank or missing speech_text falls back to usable caption."""
        session = BookSession("s-blank-speech")
        caption = "Hamlet is contemplating life and death."

        cases = [
            {"speech_text": ""},
            {"speech_text": "   "},
            {"speech_text": None},
            {},
        ]

        for payload_override in cases:
            payload = {
                "title": "Hamlet, Act 3, Scene 1",
                "caption": caption,
                "book": {"title": "Hamlet", "author": "William Shakespeare", "location": "Act 3, Scene 1"},
                **payload_override,
            }
            parsed = parse_reasoning_json(json.dumps(payload), session)
            self.assertEqual(parsed["caption"], caption)
            self.assertEqual(parsed["speech_text"], caption)
            self.assertIn(f"Illustration of {caption}", parsed["image_prompt"])

    def test_parse_reasoning_json_raises_when_both_caption_and_speech_blank(self):
        """#175: parse_reasoning_json raises ReasoningError only when both caption and speech_text are blank/missing."""
        session = BookSession("s-both-blank")

        cases = [
            {"caption": "", "speech_text": ""},
            {"caption": "   ", "speech_text": "\t \n"},
            {"caption": None, "speech_text": None},
            {},
        ]

        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(ReasoningError) as ctx:
                    parse_reasoning_json(json.dumps(payload), session)
                self.assertIn("missing both caption and speech text", str(ctx.exception).lower())

    def test_e2e_websocket_blank_caption_yields_valid_card(self):
        """#175 (REQ-WS-01): end-to-end /ws test invoking real parse_reasoning_json with blank caption yields valid Card."""
        model_json = json.dumps({
            "title": "Hamlet, Act 3, Scene 1",
            "caption": "   ",
            "speech_text": "Hamlet questions whether to endure life's troubles or take arms against them.",
            "book": {
                "title": "Hamlet",
                "author": "William Shakespeare",
                "location": "Act 3, Scene 1",
            },
            "sources": [
                {
                    "title": "Hamlet Text",
                    "url": "https://www.gutenberg.org/ebooks/1524",
                }
            ],
        })

        client = RealParserGeminiClient(model_json)
        set_reasoning_client(client)
        self.addCleanup(set_reasoning_client, None)

        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "mock-api-key", "NVIDIA_API_KEY": "", "IMAGE_BASE_URL": ""}), \
             mock.patch.object(pipeline, "draw", mock.AsyncMock(return_value=None)), \
             TestClient(app).websocket_connect("/ws") as ws:
            ws.send_json({
                "type": "invoke",
                "request_id": "req-175-card",
                "session_id": "session-175-card",
                "frame": FRAME,
                "audio": None,
                "text": "explain",
            })
            while (reply := ws.receive_json())["type"] == "status":
                pass

        self.assertEqual(reply["type"], "card", reply)
        schema_errors = [e.message for e in SCHEMA.iter_errors(reply)]
        self.assertEqual(schema_errors, [])
        self.assertEqual(
            reply["caption"],
            "Hamlet questions whether to endure life's troubles or take arms against them.",
        )
        self.assertEqual(
            reply["speech_text"],
            "Hamlet questions whether to endure life's troubles or take arms against them.",
        )
        self.assertEqual(reply["title"], "Hamlet, Act 3, Scene 1")
        self.assertEqual(reply["book"]["title"], "Hamlet")

    async def test_http_gemini_client_error_body_does_not_leak_secret(self):
        """REQ-PRIV-02: Upstream HTTP error bodies must never leak into ReasoningError or logs."""
        client = HttpGeminiClient(api_key="test-api-key")
        session = BookSession("s-privacy-http")
        err_fp = io.BytesIO(b'{"error": {"message": "SECRET_UPSTREAM_BODY_DETAILS"}}')
        http_err = urllib.error.HTTPError(
            url="https://generativelanguage.googleapis.com",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=err_fp,
        )

        with mock.patch("urllib.request.urlopen", side_effect=http_err):
            with self.assertRaises(ReasoningError) as ctx:
                await client.generate_reasoning("test question", "test page", session)

        err_msg = str(ctx.exception)
        self.assertNotIn("SECRET", err_msg)
        self.assertIn("Gemini API HTTP 500", err_msg)

        # Ensure logging the exception does not leak SECRET into logs
        logger = logging.getLogger("metalab.reasoning")
        with self.assertLogs("metalab.reasoning", level="ERROR") as cm:
            logger.error("Failed to generate reasoning: %s", ctx.exception)
        for log_line in cm.output:
            self.assertNotIn("SECRET", log_line)

    async def test_http_gemini_client_network_error_does_not_leak_secret(self):
        """REQ-PRIV-02: URLError messages/details must not leak secrets."""
        client = HttpGeminiClient(api_key="test-api-key")
        session = BookSession("s-privacy-net")

        # URLError with TimeoutError
        timeout_url_err = urllib.error.URLError(reason=TimeoutError("SECRET_NETWORK_TIMEOUT"))
        with mock.patch("urllib.request.urlopen", side_effect=timeout_url_err):
            with self.assertRaises(TimeoutError) as ctx:
                await client.generate_reasoning("test question", "test page", session)
        self.assertNotIn("SECRET", str(ctx.exception))
        self.assertEqual(str(ctx.exception), "Gemini request timed out")

        # URLError with generic exception
        net_err = urllib.error.URLError(reason=RuntimeError("SECRET_CONNECTION_REFUSED_WITH_TOKEN"))
        with mock.patch("urllib.request.urlopen", side_effect=net_err):
            with self.assertRaises(ReasoningError) as ctx:
                await client.generate_reasoning("test question", "test page", session)
        self.assertNotIn("SECRET", str(ctx.exception))
        self.assertEqual(str(ctx.exception), "Gemini API network error: RuntimeError")

    async def test_http_gemini_client_invalid_json_does_not_leak_secret(self):
        """REQ-PRIV-02: Unparseable response JSON from Gemini must not leak raw body/secret."""
        client = HttpGeminiClient(api_key="test-api-key")
        session = BookSession("s-privacy-json")
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = b"<html>SECRET_GEMINI_GATEWAY_ERROR</html>"
        mock_resp.__enter__.return_value = mock_resp

        with mock.patch("urllib.request.urlopen", return_value=mock_resp):
            with self.assertRaises(ReasoningError) as ctx:
                await client.generate_reasoning("test question", "test page", session)

        err_msg = str(ctx.exception)
        self.assertNotIn("SECRET", err_msg)
        self.assertEqual(err_msg, "Invalid JSON from Gemini API")

    def test_parse_reasoning_json_unparseable_output_does_not_leak_secret(self):
        """REQ-PRIV-02: Model output that is unparseable text must not leak in ReasoningError."""
        session = BookSession("s-privacy-parse-1")
        bad_output = "I cannot fulfill this request: SECRET_PROMPT_CONTENT_HERE"
        with self.assertRaises(ReasoningError) as ctx:
            parse_reasoning_json(bad_output, session)

        err_msg = str(ctx.exception)
        self.assertNotIn("SECRET", err_msg)
        self.assertEqual(err_msg, "Could not parse JSON from model output")

        logger = logging.getLogger("metalab.reasoning")
        with self.assertLogs("metalab.reasoning", level="ERROR") as cm:
            logger.error("Parse failed: %s", ctx.exception)
        for log_line in cm.output:
            self.assertNotIn("SECRET", log_line)

    def test_parse_reasoning_json_malformed_bracketed_output_does_not_leak_secret(self):
        """REQ-PRIV-02: Model output with malformed bracketed JSON must not leak in ReasoningError."""
        session = BookSession("s-privacy-parse-2")
        bad_json = "{'title': SECRET_UNQUOTED_VALUE}"
        with self.assertRaises(ReasoningError) as ctx:
            parse_reasoning_json(bad_json, session)

        err_msg = str(ctx.exception)
        self.assertNotIn("SECRET", err_msg)
        self.assertEqual(err_msg, "Could not parse JSON from model output")



    def test_session_candidate_books_helpers(self):
        """REQ-INTENT-01: Session candidate books tracking and deduplication."""
        session = BookSession("cand-1", book=BookInfo(title="Hamlet", author="William Shakespeare"))
        self.assertEqual(len(session.candidate_books), 1)
        self.assertEqual(session.candidate_books[0].title, "Hamlet")

        # Add duplicate by case/whitespace
        session.add_candidate_book(BookInfo(title="  hamlet  ", author="W. Shakespeare", location="Act 2"))
        self.assertEqual(len(session.candidate_books), 1)
        self.assertEqual(session.candidate_books[0].author, "W. Shakespeare")
        self.assertEqual(session.book.author, "W. Shakespeare")

        # Add second book
        session.add_candidate_book(BookInfo(title="Macbeth", author="William Shakespeare"))
        self.assertEqual(len(session.candidate_books), 2)

        # Set active book to existing candidate
        session.set_active_book("Macbeth", location="Act 1, Scene 3")
        self.assertEqual(session.book.title, "Macbeth")
        self.assertEqual(session.book.location, "Act 1, Scene 3")

        # Set active book to new book
        session.set_active_book("The Tempest", "Shakespeare", "Act 1, Scene 1")
        self.assertEqual(len(session.candidate_books), 3)
        self.assertEqual(session.book.title, "The Tempest")

    def test_ground_passage_hamlet_millisecond_local_lookup(self):
        """REQ-SRC-01: Local Hamlet grounding citations & millisecond local lookup."""
        query = "To be, or not to be, that is the question:"
        t0 = time.perf_counter()
        match = ground_passage(query)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        self.assertIsNotNone(match)
        self.assertEqual(match.play_title, "Hamlet")
        self.assertEqual(match.act, 3)
        self.assertEqual(match.scene, 1)
        self.assertEqual(match.line_start, 64)
        self.assertIn("Act 3, Scene 1", match.location)
        self.assertEqual(match.author, "William Shakespeare")
        self.assertEqual(match.source["title"], "Hamlet, public-domain text")
        self.assertEqual(match.source["url"], "https://www.gutenberg.org/ebooks/1524")
        self.assertGreaterEqual(match.score, 0.90)
        # Fast local in-memory lookup must complete in milliseconds
        self.assertLess(elapsed_ms, 50.0, f"Local lookup took {elapsed_ms:.2f}ms, expected < 50ms")

    async def test_think_wires_automatic_passage_grounding(self):
        """REQ-SRC-01: think() automatically grounds visible Hamlet passage without guessing."""
        session_id = "ground-test-1"
        command = "Explain what Hamlet is struggling with"
        passage = "To be, or not to be, that is the question: Whether 'tis nobler in the mind to suffer"

        answer = await think(command, passage, session_id, client=StubGeminiClient())

        self.assertEqual(answer["book"]["title"], "Hamlet")
        self.assertEqual(answer["book"]["author"], "William Shakespeare")
        self.assertIn("Act 3, Scene 1", answer["book"]["location"])
        self.assertTrue(len(answer["sources"]) > 0)
        self.assertEqual(answer["sources"][0]["url"], "https://www.gutenberg.org/ebooks/1524")

        session = default_session_store.get(session_id)
        self.assertIsNotNone(session)
        self.assertIn("Act 3, Scene 1", session.book.location)

    async def test_unknown_book_explicit_no_source_text_path(self):
        """REQ-SRC-01: When no local passage matches (e.g. unknown book), do not invent coordinates or fallback to Hamlet sources."""
        session_id = "unknown-book-session"
        store = SessionStore()
        session = store.get_or_create(
            session_id,
            default_book=BookInfo(title="The Great Gatsby", author="F. Scott Fitzgerald", location="Chapter 1"),
        )

        unknown_passage = "In my younger and more vulnerable years my father gave me some advice"
        command = "What advice did his father give?"

        # Local grounding must return None for unknown text/book
        match = ground_passage(unknown_passage, play="The Great Gatsby")
        self.assertIsNone(match)

        answer = await think(
            command=command,
            page_text=unknown_passage,
            session_id=session_id,
            client=StubGeminiClient(),
            session_store=store,
        )

        self.assertEqual(answer["book"]["title"], "The Great Gatsby")
        self.assertEqual(answer["book"]["author"], "F. Scott Fitzgerald")
        # sources must be empty list - no fabricated Gutenberg Hamlet URL
        self.assertEqual(answer["sources"], [])

    async def test_brand_new_session_non_hamlet_page_names_identified_or_unknown_book(self):
        """#231 REQ-SRC-01: When no passage is verified and page does not look like session's default book,
        the card names the identified book or 'Unknown book' instead of Hamlet, without overwriting session.book."""
        store = SessionStore()
        # Brand-new session starts with default Hamlet
        session_id = "s-brand-new-moby"
        session = store.get_or_create(session_id)
        self.assertEqual(session.book.title, "Hamlet")
        self.assertEqual(session.book.author, "William Shakespeare")

        # Non-Hamlet page: Moby-Dick
        moby_page = "Call me Ishmael. Some years ago, never mind how long precisely"
        command = "explain this passage"
        answer = await think(command, moby_page, session_id, client=StubGeminiClient(), session_store=store)

        self.assertNotEqual(answer["book"]["title"], "Hamlet")
        self.assertEqual(answer["book"]["title"], "Moby-Dick")
        self.assertNotEqual(answer["book"]["author"], "William Shakespeare")
        self.assertEqual(answer["book"]["author"], "Herman Melville")
        self.assertEqual(answer["sources"], [])
        # Crucially: session.book is NOT overwritten by an unverified guess
        self.assertEqual(session.book.title, "Hamlet")
        self.assertEqual(session.book.author, "William Shakespeare")

        # Another brand-new session with completely unrecognized text
        session_id_unk = "s-brand-new-unk"
        session_unk = store.get_or_create(session_id_unk)
        unk_page = "Quantum decoherence in macroscopic wavefunctions leads to classical behavior."
        answer_unk = await think(command, unk_page, session_id_unk, client=StubGeminiClient(), session_store=store)

        self.assertEqual(answer_unk["book"]["title"], "Unknown book")
        self.assertEqual(answer_unk["book"]["author"], "Unknown author")
        self.assertEqual(answer_unk["sources"], [])
        self.assertEqual(session_unk.book.title, "Hamlet")

    async def test_hamlet_page_still_grounds_exactly_and_retains_canonical_citations(self):
        """#231 REQ-SRC-01: A Hamlet page still grounds exactly with Act/Scene/Line and Gutenberg source citation."""
        store = SessionStore()
        session_id = "s-hamlet-exact"
        session = store.get_or_create(session_id)
        hamlet_page = "To be, or not to be, that is the question: Whether 'tis nobler in the mind to suffer"
        command = "explain this passage"

        answer = await think(command, hamlet_page, session_id, client=StubGeminiClient(), session_store=store)

        self.assertEqual(answer["book"]["title"], "Hamlet")
        self.assertEqual(answer["book"]["author"], "William Shakespeare")
        self.assertTrue(answer["book"]["location"].startswith("Act 3, Scene 1"))
        self.assertTrue(len(answer["sources"]) > 0)
        self.assertEqual(answer["sources"][0]["url"], "https://www.gutenberg.org/ebooks/1524")
        self.assertEqual(session.book.title, "Hamlet")
        self.assertTrue(session.book.location.startswith("Act 3, Scene 1"))

    def test_parse_reasoning_json_unknown_book_strips_fabricated_hamlet_sources(self):
        """REQ-SRC-01: Model output for non-Hamlet book never retains silent DEFAULT_HAMLET_SOURCES fallback."""
        session = BookSession("s-gatsby", book=BookInfo(title="The Great Gatsby", author="F. Scott Fitzgerald"))
        payload_no_sources = {
            "title": "The Great Gatsby, Chapter 1",
            "caption": "Nick Carraway reflects on his father's advice.",
            "speech_text": "Nick Carraway begins by recalling advice his father gave him.",
            "book": {"title": "The Great Gatsby", "author": "F. Scott Fitzgerald", "location": "Chapter 1"},
        }
        parsed = parse_reasoning_json(json.dumps(payload_no_sources), session)
        self.assertEqual(parsed["sources"], [])

        # Even if model returned Gutenberg Hamlet URL by hallucination, it is stripped
        payload_hallucinated = {
            **payload_no_sources,
            "sources": [{"title": "Hamlet", "url": "https://www.gutenberg.org/ebooks/1524"}],
        }
        parsed2 = parse_reasoning_json(json.dumps(payload_hallucinated), session)
        self.assertEqual(parsed2["sources"], [])

    def test_ground_passage_rejects_short_text(self):
        """Thread 1 (PRRT_kwDOVtZPtc63ic67): short text must not trigger a book change."""
        self.assertIsNone(ground_passage("He."))
        self.assertIsNone(ground_passage("To be."))
        self.assertIsNone(ground_passage("not to be"))  # 3 words
        # Four words still below threshold
        self.assertIsNone(ground_passage("To be or not"))
        # Long enough passage still matches
        self.assertIsNotNone(ground_passage("To be, or not to be, that is the question"))

    def test_no_passage_match_forces_empty_sources(self):
        """Thread 2 (PRRT_kwDOVtZPtc63ic6_): absence of passage_match forces sources==[] regardless of title/URL."""
        # parse_reasoning_json with Hamlet book, no passage_match, model returned Hamlet URL
        session = BookSession("s-thread2-parse")
        payload = {
            "title": "Hamlet, Act 3, Scene 1",
            "caption": "Test caption.",
            "speech_text": "Test speech.",
            "image_prompt": "Test prompt, black background (#000000).",
            "book": {"title": "Hamlet", "author": "William Shakespeare", "location": "Act 3, Scene 1"},
            "sources": [{"title": "Hamlet", "url": "https://www.gutenberg.org/ebooks/1524"}],
        }
        parsed = parse_reasoning_json(json.dumps(payload), session, passage_match=None)
        self.assertEqual(parsed["sources"], [], "parse_reasoning_json must return [] when passage_match is None")

    async def test_no_passage_match_forces_empty_sources_in_think(self):
        """Thread 2 (PRRT_kwDOVtZPtc63ic6_): think() forces sources==[] when passage_match stays None."""
        # Text that won't match any play (non-Shakespeare gibberish with enough words)
        page = "xyzzy quux corge thud wibble wobble flob nope unrecognized filler text completely."
        answer = await think("What is happening?", page, "sess-thread2-think",
                             client=StubGeminiClient())
        self.assertEqual(answer["sources"], [], "think must return sources=[] when no passage_match")

    async def test_compat_fallback_uses_inspect_not_retry(self):
        """Thread 3 (PRRT_kwDOVtZPtc63ic7D): think() uses inspect.signature, not try/except TypeError."""
        class LegacyClient:
            """Client whose generate_reasoning lacks passage_match parameter."""
            async def generate_reasoning(self, command, page_text, session, model=DEFAULT_MODEL_REASON):
                return {
                    "title": "Hamlet, Act 3, Scene 1",
                    "caption": "Legacy caption.",
                    "speech_text": "Legacy speech.",
                    "image_prompt": "Legacy prompt, black background (#000000).",
                    "book": {"title": "Hamlet", "author": "William Shakespeare", "location": "Act 3, Scene 1"},
                    "sources": [],
                }

        # LegacyClient has no passage_match param; think() must call it without that arg, no retry
        answer = await think("What happens?", "xyzzy quux corge thud wibble nope unrecognized here.",
                             "sess-thread3-legacy", client=LegacyClient())
        self.assertIn("title", answer)

        class RaisesInternalTypeError:
            """Client that raises TypeError inside the call body (not from wrong signature)."""
            async def generate_reasoning(self, command, page_text, session,
                                         model=DEFAULT_MODEL_REASON, passage_match=None):
                raise TypeError("internal bug not signature mismatch")

        with self.assertRaises(TypeError):
            await think("test", "some text with enough words here now ok.", "sess-thread3-err",
                        client=RaisesInternalTypeError())

    def test_session_record_seen_passage_text_only_and_deduping(self):
        """REQ-REASON-01: seen_passages text-only validation and consecutive deduping."""
        session = BookSession("s-seen-1")
        self.assertEqual(session.seen_passages, [])

        # Non-string raises TypeError
        with self.assertRaises(TypeError):
            session.record_seen_passage(12345)  # type: ignore

        with self.assertRaises(TypeError):
            session.record_seen_passage({"passage": "dict"})  # type: ignore

        # Clean string gets recorded
        session.record_seen_passage("  To be, or not to be  ")
        self.assertEqual(session.seen_passages, ["To be, or not to be"])

        # Consecutive duplicate is ignored
        session.record_seen_passage("To be, or not to be")
        self.assertEqual(session.seen_passages, ["To be, or not to be"])

        # Distinct passage is recorded
        session.record_seen_passage("Whether 'tis nobler in the mind to suffer")
        self.assertEqual(len(session.seen_passages), 2)

        # Non-consecutive duplicate is recorded
        session.record_seen_passage("To be, or not to be")
        self.assertEqual(len(session.seen_passages), 3)

        # Empty and whitespace passages are skipped
        session.record_seen_passage("")
        session.record_seen_passage("   \n\t  ")
        self.assertEqual(len(session.seen_passages), 3)

    def test_session_record_seen_passage_monotonic_position_tracking(self):
        """REQ-REASON-01: max_position monotonic forward advancement."""
        session = BookSession("s-pos-1")
        self.assertIsNone(session.max_position)

        # Initial position
        session.record_seen_passage("snippet 1", act=1, scene=2, line=15)
        self.assertEqual(session.max_position, (1, 2, 15))

        # Advances forward within same scene
        session.record_seen_passage("snippet 2", act=1, scene=2, line=30)
        self.assertEqual(session.max_position, (1, 2, 30))

        # Does NOT regress backwards on earlier line in same scene
        session.record_seen_passage("snippet 3", act=1, scene=2, line=10)
        self.assertEqual(session.max_position, (1, 2, 30))

        # Does NOT regress backwards on earlier scene in same act
        session.record_seen_passage("snippet 4", act=1, scene=1, line=50)
        self.assertEqual(session.max_position, (1, 2, 30))

        # Advances forward to later act
        session.record_seen_passage("snippet 5", act=3, scene=1, line=64)
        self.assertEqual(session.max_position, (3, 1, 64))

        # Line None/0 does not regress a higher line
        session.record_seen_passage("snippet 6", act=3, scene=1, line=None)
        self.assertEqual(session.max_position, (3, 1, 64))

    def test_get_reading_horizon_summary(self):
        """REQ-REASON-01: get_reading_horizon_summary never trusts ungrounded book.location."""
        session = BookSession("s-horizon-1", book=BookInfo(location="Act 5, Scene 2"))

        # When max_position is None and no passage seen, returns empty string (never guessed book.location)
        self.assertEqual(session.get_reading_horizon_summary(), "")

        # When only unverified passage text was seen (no coordinates), returns unknown-position boundary
        session.record_seen_passage("Some unrecognized page text")
        summary_unverified = session.get_reading_horizon_summary()
        self.assertIn("unknown", summary_unverified.lower())
        self.assertNotIn("Act 5", summary_unverified)

        # When max_position has line=0, returns Act and Scene
        session.record_seen_passage("line 0 test", act=2, scene=2)
        self.assertEqual(session.get_reading_horizon_summary(), "Act 2, Scene 2")

        # When max_position has line > 0, returns Act, Scene, and line
        session.record_seen_passage("line 68 test", act=3, scene=1, line=68)
        self.assertEqual(session.get_reading_horizon_summary(), "Act 3, Scene 1, line 68")

    def test_book_switch_isolates_reading_horizon_and_seen_passages(self):
        """PR #221 review: switching books isolates max_position and seen_passages per book."""
        session = BookSession("s-switch-horizon", book=BookInfo(title="Hamlet"))
        session.record_seen_passage("Now cracks a noble heart.", act=5, scene=2, line=359)
        self.assertEqual(session.max_position, (5, 2, 359))
        self.assertEqual(session.get_reading_horizon_summary(), "Act 5, Scene 2, line 359")

        # Switch to Macbeth -> must NOT inherit Hamlet Act 5 horizon or seen passages
        session.set_active_book("Macbeth", "William Shakespeare", "")
        self.assertIsNone(session.max_position)
        self.assertEqual(session.seen_passages, [])
        self.assertEqual(session.get_reading_horizon_summary(), "")

        session.record_seen_passage("Fair is foul, and foul is fair", act=1, scene=1, line=12)
        self.assertEqual(session.max_position, (1, 1, 12))

        # Switching back to Hamlet restores Hamlet's Act 5 progress cleanly
        session.set_active_book("Hamlet")
        self.assertEqual(session.max_position, (5, 2, 359))
        self.assertEqual(session.seen_passages, ["Now cracks a noble heart."])

    async def test_ungrounded_response_does_not_advance_horizon_via_guessed_location(self):
        """PR #221 review: ungrounded answer with guessed Act 5 location does not pollute horizon."""
        class _GuessingClient:
            async def generate_reasoning(self, command, page_text, session, model=DEFAULT_MODEL_REASON, passage_match=None, spoiler_guard=False):
                return {
                    "title": "Unknown Novel, Act 5, Scene 2",
                    "caption": "Guessed later scene.",
                    "speech_text": "Guessed later scene.",
                    "image_prompt": "Minimal line art, pure black background (#000000).",
                    "book": {"title": "Unknown Novel", "author": "Unknown", "location": "Act 5, Scene 2"},
                    "sources": [],
                }

        store = SessionStore()
        await think(
            "What is happening here?",
            "Unrecognized passage not in Hamlet corpus at all.",
            "s-ungrounded-horizon",
            client=_GuessingClient(),
            session_store=store,
            spoiler_guard=True,
        )
        session = store.get("s-ungrounded-horizon")
        self.assertIsNotNone(session)
        self.assertIsNone(session.max_position)
        self.assertNotIn("Act 5", session.book.location)
        self.assertNotIn("Act 5", session.get_reading_horizon_summary())

    async def test_think_advances_reading_horizon_automatically(self):
        """REQ-REASON-01: think() records seen passages and monotonically advances max_position."""
        session_id = "s-think-horizon"
        # First query grounds to Act 3, Scene 1 (line 64)
        p1 = "To be, or not to be, that is the question:"
        await think("what is this?", p1, session_id, client=StubGeminiClient())

        session = default_session_store.get(session_id)
        self.assertIsNotNone(session)
        self.assertIsNotNone(session.max_position)
        self.assertEqual(session.max_position[0], 3)
        self.assertEqual(session.max_position[1], 1)
        self.assertEqual(session.max_position[2], 64)
        self.assertEqual(session.get_reading_horizon_summary(), "Act 3, Scene 1, line 64")
        self.assertIn("To be, or not to be", session.seen_passages[0])

        # Second query with earlier passage (Act 1, Scene 2) must not regress reading horizon
        p2 = "A little more than kin, and less than kind."
        await think("who says this?", p2, session_id, client=StubGeminiClient())
        self.assertEqual(session.max_position, (3, 1, 64))
        self.assertEqual(session.get_reading_horizon_summary(), "Act 3, Scene 1, line 64")
        self.assertEqual(len(session.seen_passages), 2)

    async def test_stub_gemini_client_spoiler_guard_true_vs_false(self):
        """REQ-VOICE-02: StubGeminiClient respects spoiler_guard=True without leaking later-act reveals."""
        session_id = "s-spoiler-stub"
        stub = StubGeminiClient()
        store = SessionStore()
        session = store.get_or_create(session_id, default_book=BookInfo(title="Hamlet", location="Act 3, Scene 1"))
        session.record_seen_passage("To be or not to be", act=3, scene=1, line=68)

        spoiler_cmd = "Does Hamlet die at the end of Act 5?"

        # spoiler_guard=False -> leaks Act 5 ending
        ans_spoiled = await think(
            spoiler_cmd,
            "To be or not to be",
            session_id,
            client=stub,
            session_store=store,
            spoiler_guard=False,
        )
        self.assertIn("Act 5", ans_spoiled["caption"])
        self.assertIn("dies", ans_spoiled["caption"])
        self.assertIn("kills Claudius", ans_spoiled["speech_text"])

        # spoiler_guard=True -> guards reading horizon and suppresses Act 5 reveal
        ans_safe = await think(
            spoiler_cmd,
            "To be or not to be",
            session_id,
            client=stub,
            session_store=store,
            spoiler_guard=True,
        )
        self.assertIn("Avoiding spoilers beyond Act 3, Scene 1, line 68", ans_safe["caption"])
        self.assertIn("Without spoiling events after Act 3, Scene 1, line 68", ans_safe["speech_text"])
        self.assertNotIn("Act 5", ans_safe["caption"])

        # DECISION_ENABLE_SPOILER_CHECK env var forces spoiler_guard=True even if param is False
        with mock.patch.dict(os.environ, {"DECISION_ENABLE_SPOILER_CHECK": "1"}):
            ans_env = await think(
                spoiler_cmd,
                "To be or not to be",
                session_id,
                client=stub,
                session_store=store,
                spoiler_guard=False,
            )
            self.assertIn("Avoiding spoilers", ans_env["caption"])
            self.assertNotIn("Act 5", ans_env["caption"])

    async def test_http_gemini_client_prompt_includes_anti_spoiler_instruction(self):
        """REQ-VOICE-02: HttpGeminiClient prompt includes anti-spoiler instruction and horizon when enabled."""
        client = HttpGeminiClient(api_key="test-api-key")
        session = BookSession("s-http-spoiler", book=BookInfo(title="Hamlet", location="Act 1, Scene 5"))
        session.record_seen_passage("Ghost passage", act=1, scene=5, line=40)

        captured_body: Dict[str, Any] = {}

        def mock_urlopen(req, timeout=None):
            nonlocal captured_body
            captured_body = json.loads(req.data.decode("utf-8"))
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = json.dumps({
                "candidates": [{
                    "content": {
                        "parts": [{
                            "text": json.dumps({
                                "title": "Hamlet, Act 1, Scene 5",
                                "caption": "Ghost speaks.",
                                "speech_text": "The ghost reveals the murder.",
                                "book": {"title": "Hamlet", "author": "William Shakespeare", "location": "Act 1, Scene 5"},
                                "sources": [],
                            })
                        }]
                    }
                }]
            }).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            return mock_resp

        # 1. spoiler_guard=False, env var unset -> no anti-spoiler prompt block
        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            await client.generate_reasoning("explain", "passage text", session, spoiler_guard=False)

        user_content = captured_body["contents"][-1]["parts"][0]["text"]
        self.assertNotIn("Anti-Spoiler Guard ACTIVE", user_content)
        self.assertNotIn("Do NOT spoil plot events", user_content)

        # 2. spoiler_guard=True -> anti-spoiler block and reading horizon injected
        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            await client.generate_reasoning("explain", "passage text", session, spoiler_guard=True)

        user_content_guarded = captured_body["contents"][-1]["parts"][0]["text"]
        self.assertIn("Anti-Spoiler Guard ACTIVE", user_content_guarded)
        self.assertIn("Act 1, Scene 5, line 40", user_content_guarded)
        self.assertIn(
            "Do NOT spoil plot events, fates, or reveals occurring AFTER the student's current reading horizon",
            user_content_guarded,
        )

        # 3. DECISION_ENABLE_SPOILER_CHECK="true" env var -> activates even with spoiler_guard=False
        with mock.patch.dict(os.environ, {"DECISION_ENABLE_SPOILER_CHECK": "true"}), \
             mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            await client.generate_reasoning("explain", "passage text", session, spoiler_guard=False)

        user_content_env = captured_body["contents"][-1]["parts"][0]["text"]
        self.assertIn("Anti-Spoiler Guard ACTIVE", user_content_env)
        self.assertIn("Act 1, Scene 5, line 40", user_content_env)


    async def test_asks_future_spoiler_whole_word_matching(self):
        """REQ-VOICE-02: spoiler keywords match whole words only (\\b boundaries)."""
        from ai.reasoning import _SPOILER_RE

        # True-positives: "die" and inflections as whole words
        for phrase in ["does hamlet die?", "hamlet dies", "hamlet died", "hamlet dying"]:
            self.assertIsNotNone(_SPOILER_RE.search(phrase), f"expected match: {phrase!r}")

        # False-positive guard: "die" embedded inside "soldier", "end" in "friend"/"attend"/"pretend"
        for phrase in ["explain what the soldier said", "friend", "attend", "pretend"]:
            self.assertIsNone(_SPOILER_RE.search(phrase), f"unexpected match: {phrase!r}")

        # Integration: "Does Hamlet die?" still routes to Act 5 stub branch (guard off)
        stub = StubGeminiClient()
        store = SessionStore()
        ans_die = await think(
            "Does Hamlet die?", "passage", "s-spoiler-wbdy-die",
            client=stub, session_store=store, spoiler_guard=False,
        )
        self.assertIn("Act 5", ans_die["caption"])

        # Integration: command containing "soldier" (with embedded "die") does NOT trigger spoiler
        ans_soldier = await think(
            "explain what the soldier said", "passage", "s-spoiler-wbdy-soldier",
            client=stub, session_store=store, spoiler_guard=False,
        )
        self.assertNotIn("Act 5", ans_soldier["caption"])

    def test_ground_passage_unknown_book_returns_hamlet_match_without_filenotfound(self):
        """Acceptance check 4 (#258): ground_passage(play="Unknown book") returns a Hamlet match for Hamlet text and never logs FileNotFoundError."""
        import logging
        hamlet_text = "To be, or not to be, that is the question: Whether 'tis nobler in the mind to suffer"
        logger = logging.getLogger("metalab.reasoning")
        records = []

        class Handler(logging.Handler):
            def emit(self, record):
                records.append(record)

        h = Handler()
        logger.addHandler(h)
        try:
            match = ground_passage(hamlet_text, play="Unknown book")
        finally:
            logger.removeHandler(h)

        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.play_title, "Hamlet")
        self.assertEqual(match.act, 3)
        self.assertEqual(match.scene, 1)
        for r in records:
            self.assertNotIn("FileNotFoundError", r.getMessage())

    def test_get_gemini_turns_replays_at_most_3_exchanges_without_passage_text(self):
        """Acceptance check 5 (#258): get_gemini_turns replays at most 3 exchanges without passage text."""
        session = BookSession("s-gemini-turns-limit")
        for i in range(1, 6):
            session.add_exchange(
                question=f"Question {i}?",
                answer=f"Answer {i}.",
                passage=f"Passage for question {i}.",
            )
        turns = session.get_gemini_turns()
        # 3 exchanges * 2 turns (user + model) = 6 turns
        self.assertEqual(len(turns), 6)
        user_turns = [t for t in turns if t["role"] == "user"]
        self.assertEqual(len(user_turns), 3)
        for t in user_turns:
            text = t["parts"][0]["text"]
            self.assertNotIn("Passage", text)
            self.assertTrue(text.startswith("Question:"))

    def test_parse_gemini_response_concatenates_all_parts(self):
        """Fix #251: _parse_gemini_response concatenates all text parts across parts."""
        client = HttpGeminiClient(api_key="fake-key")
        session = BookSession("s-multipart")
        raw_json = json.dumps({
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": '{"title": "Hamlet", "caption": "Two-line caption.',},
                            {"text": ' Second line.", "speech_text": "Spoken text.", "image_prompt": "Prompt.", "book": {"title": "Hamlet"}, "sources": []}'},
                        ]
                    }
                }
            ]
        })
        parsed = client._parse_gemini_response(raw_json, session)
        self.assertEqual(parsed["caption"], "Two-line caption. Second line.")
        self.assertEqual(parsed["speech_text"], "Spoken text.")


class GeminiPartsParsingTest(unittest.TestCase):
    """#251 (REQ-REASON-01): the HTTP reasoning client reads every non-thought text part."""

    CARD_JSON = json.dumps({
        "title": "Hamlet, Act 3, Scene 1",
        "caption": "Hamlet weighs enduring life's troubles against ending them.",
        "speech_text": "Hamlet weighs enduring life's troubles against ending them.",
        "book": {"title": "Hamlet", "author": "William Shakespeare", "location": "Act 3, Scene 1"},
        "sources": [{"title": "Hamlet Text", "url": "https://www.gutenberg.org/ebooks/1524"}],
    })

    def _parse(self, parts):
        payload = json.dumps({"candidates": [{"content": {"parts": parts}}]})
        session = BookSession(session_id="s-251")
        return HttpGeminiClient(api_key="mock-gemini-key")._parse_gemini_response(payload, session)

    def test_thought_part_before_answer_is_skipped(self):
        answer = self._parse([
            {"thought": True, "text": "Thinking about Hamlet..."},
            {"text": self.CARD_JSON},
        ])
        self.assertEqual(answer["title"], "Hamlet, Act 3, Scene 1")

    def test_json_split_across_text_parts_is_joined(self):
        mid = len(self.CARD_JSON) // 2
        answer = self._parse([
            {"thought": True, "text": "Planning the card."},
            {"text": self.CARD_JSON[:mid]},
            {"text": self.CARD_JSON[mid:]},
        ])
        self.assertEqual(answer["book"]["author"], "William Shakespeare")

    def test_only_thought_parts_raises_reasoning_error(self):
        with self.assertRaises(ReasoningError):
            self._parse([{"thought": True, "text": "Thinking only."}])


if __name__ == "__main__":
    unittest.main()
