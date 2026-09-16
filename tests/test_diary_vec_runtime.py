"""Тесты конфигурации эмбеддера без обращения к сети."""

import json
import os
import unittest
from unittest.mock import patch

import diary_vec_runtime
from diary_recall_v2 import recall_v2


class EmbedRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.saved = {
            key: os.environ.get(key)
            for key in (
                "DIARY_EMBED_FAKE",
                "DIARY_EMBED_TOKEN",
                "DIARY_EMBED_BASE_URL",
                "DIARY_EMBED_MODEL",
                "DIARY_EMBED_DIM",
            )
        }
        for key in self.saved:
            os.environ.pop(key, None)
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_base_url_is_used_for_embeddings_request(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return json.dumps({"data": [{"embedding": [0.1, 0.2]}]}).encode()

        os.environ.update(
            DIARY_EMBED_TOKEN="test-token",
            DIARY_EMBED_BASE_URL="http://embed.test/v1/openai/",
            DIARY_EMBED_DIM="2",
        )
        with patch("diary_vec_runtime.urllib.request.urlopen", return_value=Response()) as urlopen:
            self.assertEqual(diary_vec_runtime.embed_texts(["текст"]), [[0.1, 0.2]])
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://embed.test/v1/openai/embeddings")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")

    def test_full_embeddings_url_is_not_duplicated(self):
        os.environ["DIARY_EMBED_BASE_URL"] = "http://embed.test/embeddings"
        self.assertEqual(
            diary_vec_runtime._embedding_url(), "http://embed.test/embeddings"
        )

    def test_hybrid_drops_weak_vector_only_tail(self):
        with patch(
            "diary_recall_v2.search_text",
            return_value=[{"id": 2, "score": 1.0, "snippet": "Docker"}],
        ), patch(
            "diary_recall_v2.search_vec",
            return_value=[{"id": 2, "score": 0.7}, {"id": 1, "score": 0.4}],
        ):
            hits = recall_v2("diary.json", "docker", k=2)
        self.assertEqual([hit["id"] for hit in hits], [2])


if __name__ == "__main__":
    unittest.main()
