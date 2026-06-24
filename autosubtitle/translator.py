from __future__ import annotations

import warnings
from dataclasses import replace

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
    def __init__(self, target_language: str, bilingual: bool) -> None:
        from deep_translator import GoogleTranslator
        from opencc import OpenCC

        self.target_language = _normalize_language_code(target_language)
        self.bilingual = bilingual
        self._translator_cls = GoogleTranslator
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
            merged_text = self._merge_text(segment.text, translated_text)
            translated_segments.append(replace(segment, text=merged_text))

        return translated_segments

    def _translate_texts(
        self,
        texts: list[str],
        source_language: str,
    ) -> list[str]:
        if not texts:
            return []

        translator = self._translator_cls(source=source_language, target=self.target_language)
        translated: list[str] = []
        failed_texts: list[str] = []

        batch_size = 50
        for batch_start in range(0, len(texts), batch_size):
            batch = texts[batch_start : batch_start + batch_size]
            try:
                translated_batch = translator.translate_batch(batch)
                translated.extend(self._coerce_batch_result(batch, translated_batch))
            except Exception:
                for text in batch:
                    if not text.strip():
                        translated.append(text)
                        continue
                    try:
                        translated_text = translator.translate(text)
                        translated.append(translated_text or text)
                    except Exception:
                        translated.append(text)
                        failed_texts.append(text)

        if failed_texts:
            warnings.warn(
                f"Translation failed for {len(failed_texts)} subtitle line(s); "
                "the original text was kept.",
                RuntimeWarning,
                stacklevel=2,
            )

        return translated

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
        converted_segments: list[SubtitleSegment] = []
        for segment in segments:
            converted_text = self._opencc.convert(segment.text)
            merged_text = self._merge_text(segment.text, converted_text)
            converted_segments.append(replace(segment, text=merged_text))
        return converted_segments
