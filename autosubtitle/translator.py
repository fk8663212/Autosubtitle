from __future__ import annotations

import json
import os
import warnings
from dataclasses import replace

from openai import OpenAI
from opencc import OpenCC

from autosubtitle.config import TranslationConfig
from autosubtitle.srt import SubtitleSegment


class SubtitleTranslator:
    def __init__(
        self,
        config: TranslationConfig,
        target_language: str | None = None,
        bilingual: bool | None = None,
    ) -> None:
        endpoint = config.endpoint
        api_key = os.getenv(endpoint.api_key_env) if endpoint.api_key_env else "local"
        if not api_key:
            raise RuntimeError(
                f"Environment variable {endpoint.api_key_env} is required for "
                f"translation mode '{config.mode}'."
            )

        self.mode = config.mode
        self.model = endpoint.model
        self.target_language = target_language or config.target_language
        self.bilingual = config.bilingual if bilingual is None else bilingual
        self.batch_size = config.batch_size
        self.client = OpenAI(
            api_key=api_key,
            base_url=endpoint.base_url,
            timeout=config.timeout_seconds,
        )
        self._opencc = OpenCC("s2twp")

    def translate_segments(
        self,
        segments: list[SubtitleSegment],
        source_language: str | None,
    ) -> list[SubtitleSegment]:
        translated_texts = self._translate_texts(
            [segment.text for segment in segments],
            source_language=source_language or "auto-detected source language",
        )
        translated_segments: list[SubtitleSegment] = []

        for segment, translated in zip(segments, translated_texts, strict=True):
            translated_text = self._postprocess_text(translated)
            merged_text = self._merge_text(segment.text, translated_text)
            translated_segments.append(replace(segment, text=merged_text))

        return translated_segments

    def _translate_texts(self, texts: list[str], source_language: str) -> list[str]:
        translated: list[str] = []
        failed_lines = 0

        for batch_start in range(0, len(texts), self.batch_size):
            batch = texts[batch_start : batch_start + self.batch_size]
            try:
                translated.extend(self._translate_batch(batch, source_language))
            except Exception as exc:
                translated.extend(batch)
                failed_lines += len(batch)
                warnings.warn(
                    f"LLM translation batch failed ({exc}); original text was kept.",
                    RuntimeWarning,
                    stacklevel=2,
                )

        if failed_lines:
            warnings.warn(
                f"Translation failed for {failed_lines} subtitle line(s).",
                RuntimeWarning,
                stacklevel=2,
            )
        return translated

    def _translate_batch(self, texts: list[str], source_language: str) -> list[str]:
        indexed_texts = [
            {"id": index, "text": text.strip()}
            for index, text in enumerate(texts)
        ]
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You translate subtitle lines. Preserve meaning, tone, names, "
                        "punctuation, and line order. Do not add explanations. Return "
                        "only a JSON array with objects containing integer 'id' and "
                        "string 'text' fields."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Translate from {source_language} to {self.target_language}. "
                        "Keep each input item as exactly one output item.\n"
                        + json.dumps(indexed_texts, ensure_ascii=False)
                    ),
                },
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("The translation model returned an empty response")
        return self._parse_translation(content, texts)

    @staticmethod
    def _parse_translation(content: str, source_texts: list[str]) -> list[str]:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            cleaned = cleaned.rsplit("```", 1)[0].strip()

        payload = json.loads(cleaned)
        if not isinstance(payload, list) or len(payload) != len(source_texts):
            raise ValueError("The translation model returned an invalid item count")

        translated = list(source_texts)
        seen_ids: set[int] = set()
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError("The translation model returned an invalid item")
            item_id = item.get("id")
            text = item.get("text")
            if (
                not isinstance(item_id, int)
                or item_id < 0
                or item_id >= len(source_texts)
                or item_id in seen_ids
                or not isinstance(text, str)
            ):
                raise ValueError("The translation model returned invalid fields")
            translated[item_id] = text
            seen_ids.add(item_id)

        if len(seen_ids) != len(source_texts):
            raise ValueError("The translation model omitted subtitle lines")
        return translated

    def _postprocess_text(self, text: str) -> str:
        if self.target_language.lower() == "zh-tw":
            return self._opencc.convert(text)
        return text

    def _merge_text(self, source_text: str, translated_text: str) -> str:
        source = source_text.strip()
        translated = translated_text.strip()
        if not translated or translated == source:
            return source
        if self.bilingual:
            return f"{source}\n{translated}"
        return translated
