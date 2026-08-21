from __future__ import annotations

import json
import os
from dataclasses import replace
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from autosubtitle.config import TranslationConfig
from autosubtitle.srt import SubtitleSegment


def _normalize_language_code(language: str) -> str:
    normalized = language.strip()
    aliases = {
        "zh_tw": "zh-TW",
        "zh-tw": "zh-TW",
        "zh_hant": "zh-TW",
        "zh-hant": "zh-TW",
        "zh_cn": "zh-CN",
        "zh-cn": "zh-CN",
        "zh_hans": "zh-CN",
        "zh-hans": "zh-CN",
        "jp": "ja",
    }
    return aliases.get(normalized.lower(), normalized)


class SubtitleTranslator:
    def __init__(
        self,
        target_language: str | None = None,
        bilingual: bool | None = None,
        provider: str = "google",
        endpoint: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        config: TranslationConfig | None = None,
    ) -> None:
        from opencc import OpenCC

        self.batch_size = 20
        self.timeout_seconds = 120.0
        if config is not None:
            configured_endpoint = config.endpoint
            provider = "openai"
            endpoint = f"{configured_endpoint.base_url.rstrip('/')}/chat/completions"
            model = configured_endpoint.model
            api_key = (
                os.getenv(configured_endpoint.api_key_env)
                if configured_endpoint.api_key_env
                else "local"
            )
            if not api_key:
                raise RuntimeError(
                    f"Environment variable {configured_endpoint.api_key_env} is required "
                    f"for translation mode '{config.mode}'."
                )
            target_language = target_language or config.target_language
            bilingual = config.bilingual if bilingual is None else bilingual
            self.batch_size = config.batch_size
            self.timeout_seconds = config.timeout_seconds

        self.target_language = _normalize_language_code(target_language or "zh-TW")
        self.bilingual = bool(bilingual)
        self.provider = provider.lower()
        if self.provider not in {"google", "ollama", "openai"}:
            raise ValueError(f"Unsupported translation provider: {provider}")
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key
        self._opencc = OpenCC("s2twp")

    def translate_segments(
        self,
        segments: list[SubtitleSegment],
        source_language: str | None,
    ) -> list[SubtitleSegment]:
        normalized_source = (
            _normalize_language_code(source_language) if source_language else "auto"
        )
        if normalized_source.lower() == self.target_language.lower():
            return segments
        if self.target_language.lower() == "zh-tw" and normalized_source.lower() in {
            "zh",
            "zh-cn",
            "zh-tw",
        }:
            return self._convert_chinese_segments(segments)

        translated_texts = self._translate_texts(
            [segment.text for segment in segments],
            source_language=normalized_source,
        )
        translated_segments: list[SubtitleSegment] = []
        for segment, translated in zip(segments, translated_texts, strict=True):
            translated_text = self._postprocess_text(translated)
            translated_segments.append(
                replace(
                    segment,
                    text=self._merge_text(segment.text, translated_text),
                )
            )
        return translated_segments

    def _translate_texts(self, texts: list[str], source_language: str) -> list[str]:
        if not texts:
            return []
        if self.provider in {"ollama", "openai"}:
            return self._translate_with_llm(texts, source_language)

        from deep_translator import GoogleTranslator

        translator = GoogleTranslator(source=source_language, target=self.target_language)
        translated: list[str] = []
        failed_texts: list[str] = []
        for batch_start in range(0, len(texts), 50):
            batch = texts[batch_start : batch_start + 50]
            try:
                translated_batch = translator.translate_batch(batch)
                translated.extend(self._coerce_batch_result(batch, translated_batch))
            except Exception:
                for text in batch:
                    if not text.strip():
                        translated.append(text)
                        continue
                    try:
                        translated.append(translator.translate(text) or text)
                    except Exception:
                        translated.append(text)
                        failed_texts.append(text)
        if failed_texts:
            raise RuntimeError(
                f"Translation failed for {len(failed_texts)} subtitle line(s); retry the job"
            )
        return translated

    def _translate_with_llm(self, texts: list[str], source_language: str) -> list[str]:
        if not self.model:
            raise ValueError(f"A model is required for the {self.provider} provider")
        translated: list[str] = []
        batch_size = getattr(self, "batch_size", 20)
        for batch_start in range(0, len(texts), batch_size):
            batch = texts[batch_start : batch_start + batch_size]
            translated.extend(self._request_llm_batch(batch, source_language))
        return translated

    def _request_llm_batch(self, texts: list[str], source_language: str) -> list[str]:
        prompt = (
            f"Translate each subtitle from {source_language} to {self.target_language}. "
            "Preserve meaning, tone, names, and line order. Do not merge or omit items. "
            "Return only a JSON object with a translations array containing exactly "
            f"{len(texts)} strings. Input: {json.dumps(texts, ensure_ascii=False)}"
        )
        messages = [
            {
                "role": "system",
                "content": "You are a precise subtitle translator. Return valid JSON only.",
            },
            {"role": "user", "content": prompt},
        ]
        if self.provider == "ollama":
            endpoint = (self.endpoint or "http://localhost:11434").rstrip("/") + "/api/chat"
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "format": {
                    "type": "object",
                    "properties": {
                        "translations": {
                            "type": "array",
                            "items": {"type": "string"},
                        }
                    },
                    "required": ["translations"],
                },
                "options": {"temperature": 0},
            }
        else:
            if not self.endpoint:
                raise ValueError("An OpenAI-compatible chat completions endpoint is required")
            endpoint = self.endpoint
            payload = {"model": self.model, "messages": messages, "temperature": 0}

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(
                request,
                timeout=getattr(self, "timeout_seconds", 120.0),
            ) as response:
                response_data = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"{self.provider} translation request failed: {exc}") from exc

        if self.provider == "ollama":
            content = response_data.get("message", {}).get("content", "")
        else:
            try:
                content = response_data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError("OpenAI-compatible API returned an invalid response") from exc
        try:
            translations = json.loads(content)["translations"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise RuntimeError("LLM translation did not return the required JSON object") from exc
        if not isinstance(translations, list) or len(translations) != len(texts):
            count = len(translations) if isinstance(translations, list) else 0
            raise RuntimeError(
                f"LLM returned {count} translations for {len(texts)} subtitles"
            )
        if not all(isinstance(item, str) for item in translations):
            raise RuntimeError("LLM translation contained a non-text result")
        return translations

    @staticmethod
    def _coerce_batch_result(
        source_texts: list[str],
        translated_batch: str | list[str] | None,
    ) -> list[str]:
        if translated_batch is None:
            raise ValueError("Translator returned no batch result")
        if isinstance(translated_batch, str):
            if len(source_texts) != 1:
                raise ValueError("Translator returned one result for multiple inputs")
            return [translated_batch]
        if len(translated_batch) != len(source_texts):
            raise ValueError("Translator returned an incomplete batch result")
        return [
            item if item is not None else source
            for source, item in zip(source_texts, translated_batch, strict=True)
        ]

    def _merge_text(self, source_text: str, translated_text: str) -> str:
        source = source_text.strip()
        translated = translated_text.strip()
        if not translated or translated == source:
            return source
        if self.bilingual:
            return f"{source}\n{translated}"
        return translated

    def _postprocess_text(self, text: str) -> str:
        if self.target_language.lower() == "zh-tw":
            return self._opencc.convert(text)
        return text

    def _convert_chinese_segments(
        self,
        segments: list[SubtitleSegment],
    ) -> list[SubtitleSegment]:
        return [
            replace(
                segment,
                text=self._merge_text(segment.text, self._opencc.convert(segment.text)),
            )
            for segment in segments
        ]
