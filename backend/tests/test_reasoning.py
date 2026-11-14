import asyncio
import re
import unittest

from ai.reasoning import (
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


if __name__ == "__main__":
    unittest.main()
