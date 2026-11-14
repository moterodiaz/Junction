import asyncio
import io
import json
import logging
import os
from pathlib import Path
import re
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


if __name__ == "__main__":
    unittest.main()
