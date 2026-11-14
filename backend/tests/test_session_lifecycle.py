"""#139 / REQ-PRIV-03: a book session, its spoken clips and its images end together, after an idle
TTL, and no ended session's media can be fetched. Sessions stay isolated from each other."""

import asyncio
import os
import time
import unittest
from unittest import mock

from fastapi.testclient import TestClient

import ai.image as image
from ai.session import default_session_store
from app import pipeline
from app.main import app
from stt import speak


class SessionLifecycleTest(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {"GEMINI_API_KEY": "", "NVIDIA_API_KEY": "", "IMAGE_BASE_URL": "https://metalab.example"})
        env.start()
        self.addCleanup(env.stop)
        default_session_store.clear()
        speak.clear()
        image.clear_all_images()
        self.addCleanup(default_session_store.clear)
        self.addCleanup(speak.clear)
        self.addCleanup(image.clear_all_images)
        pipeline._SESSION_SEEN.clear()
        self.addCleanup(pipeline._SESSION_SEEN.clear)

    def seed(self, session_id):
        """Give a session a history, a non-default book, a clip and an image, as a card would."""
        session = default_session_store.get_or_create(session_id)
        session.add_exchange(question="what is this?", answer="a passage", passage="text")
        session.set_active_book("Macbeth", "William Shakespeare", "Act 1, Scene 3")
        clip = speak.store(b"RIFF", session_id)
        img = image.store_image(f"img-{session_id}", b"\x89PNG", session_id=session_id)
        return clip, img.image_id

    def test_two_sessions_never_see_each_others_history_or_media(self):
        self.seed("alice")
        self.seed("bob")
        alice = default_session_store.get_or_create("alice")
        bob = default_session_store.get_or_create("bob")
        self.assertEqual([e.question for e in alice.history], ["what is this?"])
        self.assertIsNot(alice.history, bob.history)
        self.assertEqual(speak.cleanup_session("alice"), 1)
        self.assertEqual(len(default_session_store.get_or_create("bob").history), 1)

    def test_an_idle_session_is_ended_with_its_clips_and_images(self):
        clip, img_id = self.seed("idle")
        pipeline._touch("idle")
        with mock.patch.object(pipeline, "SESSION_IDLE_TTL_S", 60):
            ended = pipeline.sweep_expired(now=time.monotonic() + 61)
        self.assertEqual(ended, ["idle"])
        self.assertIsNone(default_session_store.get("idle"))
        self.assertIsNone(speak.get(clip))
        self.assertIsNone(image.get_image(img_id))

    def test_expired_audio_and_images_cannot_be_fetched(self):
        clip, img_id = self.seed("gone")
        client = TestClient(app)
        # positive control: both are fetchable while the session is live, so the 404s below mean something
        self.assertEqual(client.get(f"/audio/{clip}.wav").status_code, 200)
        self.assertEqual(client.get(f"/img/{img_id}").status_code, 200)
        pipeline.end_session("gone")
        self.assertEqual(client.get(f"/audio/{clip}.wav").status_code, 404)
        self.assertEqual(client.get(f"/img/{img_id}").status_code, 404)

    def test_a_busy_session_is_never_expired_mid_request(self):
        self.seed("busy")
        pipeline._touch("busy")
        lock = asyncio.Lock()
        pipeline._SESSION_LOCKS["busy"] = lock

        async def hold():
            async with lock:
                with mock.patch.object(pipeline, "SESSION_IDLE_TTL_S", 60):
                    return pipeline.sweep_expired(now=time.monotonic() + 10_000)
        self.assertEqual(asyncio.run(hold()), [])
        self.assertIsNotNone(default_session_store.get("busy"))

    def test_an_idle_session_expires_on_the_next_request_and_starts_fresh(self):
        self.seed("ended")
        pipeline._touch("ended")
        with mock.patch.object(pipeline, "SESSION_IDLE_TTL_S", 60):
            expired = pipeline.sweep_expired(now=time.monotonic() + 61)
        self.assertIn("ended", expired)
        fresh = default_session_store.get_or_create("ended")
        self.assertEqual(fresh.history, [])
        self.assertEqual(fresh.book.title, "Hamlet")  # the default book, not the abandoned Macbeth

    def test_a_recent_session_is_kept(self):
        self.seed("active")
        pipeline._touch("active")
        with mock.patch.object(pipeline, "SESSION_IDLE_TTL_S", 3600):
            self.assertEqual(pipeline.sweep_expired(), [])
        self.assertIsNotNone(default_session_store.get("active"))


if __name__ == "__main__":
    unittest.main()
