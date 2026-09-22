"""Turning a Bengali search into something the English catalogue can be matched against.

Customers type product names in Bengali — নেটফ্লিক্স, ক্যানভা — while the catalogue is
written in English. Two things bridge that, in this order:

1.  A short list of the words this shop actually sells. Bengali writes an abbreviation the
    way it sounds, so ভিপিএন is "bhipien" letter by letter and no amount of phonetics turns
    it into "vpn". These are the cases spelling cannot reach, and there are not many of
    them, because a catalogue of well-known brands repeats the same few words.
2.  Letter-by-letter transliteration for everything else, which handles the brand names
    that are simply spelled out: নেটফ্লিক্স becomes "netphliks", close enough for the
    trigram match that follows to find "Netflix".

Neither is exact, and neither has to be: what comes out is fed to a similarity search, not
compared for equality.
"""

from __future__ import annotations

import re

# Words a phonetic reading cannot reach, mostly abbreviations and names Bengali spells its
# own way. Extend this rather than adding keywords to every product.
SYNONYMS: dict[str, str] = {
    "ভিপিএন": "vpn",
    "প্রক্সি": "proxy",
    "প্রোক্সি": "proxy",
    "মেইল": "mail",
    "মেল": "mail",
    "ইমেইল": "email mail",
    "নেটফ্লিক্স": "netflix",
    "ক্যানভা": "canva",
    "কেনভা": "canva",
    "স্পটিফাই": "spotify",
    "ইউটিউব": "youtube",
    "টেলিগ্রাম": "telegram",
    "জিমেইল": "gmail",
    "আউটলুক": "outlook",
    "চ্যাটজিপিটি": "chatgpt",
    "জিপিটি": "gpt chatgpt",
    "মিডজার্নি": "midjourney",
    "গিটহাব": "github",
    "কপাইলট": "copilot",
    "জেমিনি": "gemini",
    "ক্লদ": "claude",
    "অফিস": "office",
    "উইন্ডোজ": "windows",
    "সাবস্ক্রিপশন": "subscription",
    "প্রিমিয়াম": "premium",
    "একাউন্ট": "account",
    "অ্যাকাউন্ট": "account",
    "মাস": "month",
    "মাসের": "month",
    "দিন": "days",
    "দিনের": "days",
    "বছর": "year",
    "প্রাইভেট": "private",
    "শেয়ার": "shared",
    "শেয়ার্ড": "shared",
}

# Independent vowels, vowel signs, consonants and digits. Bengali is written as consonant
# plus optional sign, so both forms of each vowel are needed.
_LETTERS: dict[str, str] = {
    "অ": "o", "আ": "a", "ই": "i", "ঈ": "i", "উ": "u", "ঊ": "u", "ঋ": "ri",
    "এ": "e", "ঐ": "oi", "ও": "o", "ঔ": "ou",
    "া": "a", "ি": "i", "ী": "i", "ু": "u", "ূ": "u", "ৃ": "ri",
    "ে": "e", "ৈ": "oi", "ো": "o", "ৌ": "ou",
    "ক": "k", "খ": "kh", "গ": "g", "ঘ": "gh", "ঙ": "ng",
    "চ": "ch", "ছ": "chh", "জ": "j", "ঝ": "jh", "ঞ": "n",
    "ট": "t", "ঠ": "th", "ড": "d", "ঢ": "dh", "ণ": "n",
    "ত": "t", "থ": "th", "দ": "d", "ধ": "dh", "ন": "n",
    "প": "p", "ফ": "f", "ব": "b", "ভ": "v", "ম": "m",
    "য": "j", "র": "r", "ল": "l", "শ": "sh", "ষ": "sh", "স": "s", "হ": "h",
    "ড়": "r", "ঢ়": "rh", "য়": "y", "ৎ": "t", "ং": "ng", "ঃ": "h",
    "্": "", "ঁ": "",
    "০": "0", "১": "1", "২": "2", "৩": "3", "৪": "4",
    "৫": "5", "৬": "6", "৭": "7", "৮": "8", "৯": "9",
}

_BENGALI = re.compile(r"[ঀ-৿]")


def has_bengali(text: str) -> bool:
    return bool(_BENGALI.search(text or ""))


def transliterate(text: str) -> str:
    """Read Bengali letters out in Latin. Anything already Latin is left alone."""
    return "".join(_LETTERS.get(ch, ch) for ch in text or "")


def latin_forms(text: str) -> list[str]:
    """Every spelling worth searching for, the most reliable first.

    The original is always included, because a customer may type "netflix" in Latin and a
    Bengali word in the same breath.
    """
    text = (text or "").strip()
    if not text:
        return []
    forms = [text]
    if not has_bengali(text):
        return forms

    known = [SYNONYMS[word] for word in re.split(r"\s+", text) if word in SYNONYMS]
    if known:
        forms.append(" ".join(known))
    for word, latin in SYNONYMS.items():
        if word in text and latin not in forms:
            forms.append(latin)

    spelled = transliterate(text).strip()
    if spelled and spelled not in forms:
        forms.append(spelled)
    return forms
