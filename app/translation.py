from __future__ import annotations

import threading
from typing import Any

from app.models import SubtitleSegment

MODEL_NAME = "facebook/nllb-200-distilled-600M"

WHISPER_TO_FLORES: dict[str, str] = {
    "af": "afr_Latn",
    "am": "amh_Ethi",
    "ar": "arb_Arab",
    "az": "azj_Latn",
    "be": "bel_Cyrl",
    "bg": "bul_Cyrl",
    "bn": "ben_Beng",
    "bs": "bos_Latn",
    "ca": "cat_Latn",
    "cs": "ces_Latn",
    "cy": "cym_Latn",
    "da": "dan_Latn",
    "de": "deu_Latn",
    "el": "ell_Grek",
    "en": "eng_Latn",
    "es": "spa_Latn",
    "et": "est_Latn",
    "eu": "eus_Latn",
    "fa": "pes_Arab",
    "fi": "fin_Latn",
    "fr": "fra_Latn",
    "gu": "guj_Gujr",
    "he": "heb_Hebr",
    "hi": "hin_Deva",
    "hr": "hrv_Latn",
    "hu": "hun_Latn",
    "hy": "hye_Armn",
    "id": "ind_Latn",
    "is": "isl_Latn",
    "it": "ita_Latn",
    "ja": "jpn_Jpan",
    "ka": "kat_Geor",
    "kk": "kaz_Cyrl",
    "km": "khm_Khmr",
    "kn": "kan_Knda",
    "ko": "kor_Hang",
    "lt": "lit_Latn",
    "lv": "lvs_Latn",
    "mk": "mkd_Cyrl",
    "ml": "mal_Mlym",
    "mn": "khk_Cyrl",
    "mr": "mar_Deva",
    "ms": "zsm_Latn",
    "mt": "mlt_Latn",
    "my": "mya_Mymr",
    "ne": "npi_Deva",
    "nl": "nld_Latn",
    "no": "nob_Latn",
    "pa": "pan_Guru",
    "pl": "pol_Latn",
    "ps": "pbt_Arab",
    "pt": "por_Latn",
    "ro": "ron_Latn",
    "ru": "rus_Cyrl",
    "sd": "snd_Arab",
    "si": "sin_Sinh",
    "sk": "slk_Latn",
    "sl": "slv_Latn",
    "so": "som_Latn",
    "sq": "als_Latn",
    "sr": "srp_Cyrl",
    "sv": "swe_Latn",
    "sw": "swh_Latn",
    "ta": "tam_Taml",
    "te": "tel_Telu",
    "th": "tha_Thai",
    "tl": "tgl_Latn",
    "tr": "tur_Latn",
    "uk": "ukr_Cyrl",
    "ur": "urd_Arab",
    "uz": "uzn_Latn",
    "vi": "vie_Latn",
    "zh": "zho_Hans",
}

SUPPORTED_LANGUAGES: list[dict[str, str]] = [
    {"code": "arb_Arab", "name": "Arabic"},
    {"code": "deu_Latn", "name": "German"},
    {"code": "rus_Cyrl", "name": "Russian"},
    {"code": "fra_Latn", "name": "French"},
    {"code": "kor_Hang", "name": "Korean"},
    {"code": "zho_Hans", "name": "Chinese (Simplified)"},
    {"code": "zho_Hant", "name": "Chinese (Traditional)"},
    {"code": "jpn_Jpan", "name": "Japanese"},
    {"code": "spa_Latn", "name": "Spanish"},
    {"code": "hin_Deva", "name": "Hindi"},
    {"code": "eng_Latn", "name": "English"},
    {"code": "vie_Latn", "name": "Vietnamese"},
    {"code": "ita_Latn", "name": "Italian"},
    {"code": "ind_Latn", "name": "Indonesian"},
    {"code": "por_Latn", "name": "Portuguese"},
    {"code": "tha_Thai", "name": "Thai"},
    {"code": "tur_Latn", "name": "Turkish"},
    {"code": "nld_Latn", "name": "Dutch"},
]

_model: Any = None
_tokenizer: Any = None
_load_lock = threading.Lock()


class TranslationModelUnavailable(RuntimeError):
    pass


def _get_model_and_tokenizer() -> tuple[Any, Any]:
    global _model, _tokenizer

    if _model is not None and _tokenizer is not None:
        return _model, _tokenizer

    with _load_lock:
        if _model is not None and _tokenizer is not None:
            return _model, _tokenizer

        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            import torch
        except ImportError as exc:
            raise TranslationModelUnavailable(
                "transformers and torch are required for translation. "
                "Run: pip install transformers torch sentencepiece"
            ) from exc

        device = "cuda" if torch.cuda.is_available() else "cpu"
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        _model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME).to(device)
        _model.eval()

    return _model, _tokenizer


def whisper_to_flores(whisper_lang: str | None) -> str:
    if whisper_lang is None:
        return "eng_Latn"
    return WHISPER_TO_FLORES.get(whisper_lang.lower().strip(), "eng_Latn")


def translate_segments(
    segments: list[SubtitleSegment],
    source_lang: str,
    target_lang: str,
) -> list[SubtitleSegment]:
    if not segments:
        return []

    model, tokenizer = _get_model_and_tokenizer()

    source_flores = whisper_to_flores(source_lang)
    tokenizer.src_lang = source_flores
    tokenizer.tgt_lang = target_lang

    texts = [segment.text for segment in segments]

    translated_segments: list[SubtitleSegment] = []
    batch_size = 8

    forced_bos_id = tokenizer.convert_tokens_to_ids(target_lang)

    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i : i + batch_size]
        inputs = tokenizer(
            batch_texts, return_tensors="pt", padding=True, truncation=True, max_length=256
        ).to(model.device)

        generated_tokens = model.generate(
            **inputs,
            forced_bos_token_id=forced_bos_id,
            max_length=256,
            num_beams=4,
        )
        batch_translated = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)

        for j, translated_text in enumerate(batch_translated):
            segment = segments[i + j]
            translated_segments.append(
                SubtitleSegment(
                    start=segment.start,
                    end=segment.end,
                    text=translated_text.strip(),
                )
            )

    return translated_segments
