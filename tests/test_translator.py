from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from autosubtitle.translator import SubtitleTranslator


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def make_openai_translator() -> SubtitleTranslator:
    translator = SubtitleTranslator.__new__(SubtitleTranslator)
    translator.provider = "openai"
    translator.endpoint = "http://translator.test/v1/chat/completions"
    translator.model = "translation-model"
    translator.api_key = "secret"
    translator.target_language = "zh-TW"
    return translator


class LlmTranslatorTest(unittest.TestCase):
    @patch("autosubtitle.translator.urlopen")
    def test_openai_response_keeps_subtitle_count(self, mocked_urlopen) -> None:
        mocked_urlopen.return_value = FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"translations": ["第一句", "第二句"]}
                            )
                        }
                    }
                ]
            }
        )
        result = make_openai_translator()._request_llm_batch(
            ["First", "Second"], "en"
        )
        self.assertEqual(result, ["第一句", "第二句"])

    @patch("autosubtitle.translator.urlopen")
    def test_openai_response_rejects_missing_subtitle(self, mocked_urlopen) -> None:
        mocked_urlopen.return_value = FakeResponse(
            {
                "choices": [
                    {"message": {"content": '{"translations": ["只有一句"]}'}}
                ]
            }
        )
        with self.assertRaisesRegex(RuntimeError, "translations for 2"):
            make_openai_translator()._request_llm_batch(["First", "Second"], "en")


if __name__ == "__main__":
    unittest.main()
