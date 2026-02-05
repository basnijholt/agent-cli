"""Language codes supported by Whisper ASR models.

This list is derived from the OpenAI Whisper model's supported languages.
Source: https://github.com/openai/whisper/blob/main/whisper/tokenizer.py

The codes are ISO 639-1 (2-letter) or ISO 639-2 (3-letter) codes where
2-letter codes are not available.
"""

from __future__ import annotations

# Language codes supported by Whisper models
# fmt: off
WHISPER_LANGUAGE_CODES: list[str] = [
    "af",   # Afrikaans
    "am",   # Amharic
    "ar",   # Arabic
    "as",   # Assamese
    "az",   # Azerbaijani
    "ba",   # Bashkir
    "be",   # Belarusian
    "bg",   # Bulgarian
    "bn",   # Bengali
    "bo",   # Tibetan
    "br",   # Breton
    "bs",   # Bosnian
    "ca",   # Catalan
    "cs",   # Czech
    "cy",   # Welsh
    "da",   # Danish
    "de",   # German
    "el",   # Greek
    "en",   # English
    "es",   # Spanish
    "et",   # Estonian
    "eu",   # Basque
    "fa",   # Persian
    "fi",   # Finnish
    "fo",   # Faroese
    "fr",   # French
    "gl",   # Galician
    "gu",   # Gujarati
    "ha",   # Hausa
    "haw",  # Hawaiian
    "he",   # Hebrew
    "hi",   # Hindi
    "hr",   # Croatian
    "ht",   # Haitian Creole
    "hu",   # Hungarian
    "hy",   # Armenian
    "id",   # Indonesian
    "is",   # Icelandic
    "it",   # Italian
    "ja",   # Japanese
    "jw",   # Javanese
    "ka",   # Georgian
    "kk",   # Kazakh
    "km",   # Khmer
    "kn",   # Kannada
    "ko",   # Korean
    "la",   # Latin
    "lb",   # Luxembourgish
    "ln",   # Lingala
    "lo",   # Lao
    "lt",   # Lithuanian
    "lv",   # Latvian
    "mg",   # Malagasy
    "mi",   # Maori
    "mk",   # Macedonian
    "ml",   # Malayalam
    "mn",   # Mongolian
    "mr",   # Marathi
    "ms",   # Malay
    "mt",   # Maltese
    "my",   # Myanmar (Burmese)
    "ne",   # Nepali
    "nl",   # Dutch
    "nn",   # Norwegian Nynorsk
    "no",   # Norwegian
    "oc",   # Occitan
    "pa",   # Punjabi
    "pl",   # Polish
    "ps",   # Pashto
    "pt",   # Portuguese
    "ro",   # Romanian
    "ru",   # Russian
    "sa",   # Sanskrit
    "sd",   # Sindhi
    "si",   # Sinhala
    "sk",   # Slovak
    "sl",   # Slovenian
    "sn",   # Shona
    "so",   # Somali
    "sq",   # Albanian
    "sr",   # Serbian
    "su",   # Sundanese
    "sv",   # Swedish
    "sw",   # Swahili
    "ta",   # Tamil
    "te",   # Telugu
    "tg",   # Tajik
    "th",   # Thai
    "tk",   # Turkmen
    "tl",   # Tagalog
    "tr",   # Turkish
    "tt",   # Tatar
    "uk",   # Ukrainian
    "ur",   # Urdu
    "uz",   # Uzbek
    "vi",   # Vietnamese
    "yi",   # Yiddish
    "yo",   # Yoruba
    "zh",   # Chinese
    "yue",  # Cantonese
]
# fmt: on
