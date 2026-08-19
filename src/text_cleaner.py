"""Deterministic email text cleaning before event extraction."""
from __future__ import annotations

import html
import re

BLOCK_TAG_RE = re.compile(
    r"(?is)<(br\s*/?|/p|/div|/li|/tr|/h[1-6]|/blockquote|/section|/article)[^>]*>"
)
REMOVE_BLOCK_RE = re.compile(r"(?is)<(script|style|head|title)[^>]*>.*?</\1>|<[^>]+>")
WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
NEWLINE_RE = re.compile(r"\n{3,}")
ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\ufeff\u2060]")


def html_to_text(raw: str) -> str:
    if not raw:
        return ""
    text = re.sub(r"(?is)<(script|style|head|title)[^>]*>.*?</\1>", " ", raw)
    text = BLOCK_TAG_RE.sub("\n", text)
    text = REMOVE_BLOCK_RE.sub(" ", text)
    text = html.unescape(text)
    text = ZERO_WIDTH_RE.sub("", text)
    text = WHITESPACE_RE.sub(" ", text)
    text = NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def clean_text(value: str, max_chars: int | None = None) -> str:
    text = html_to_text(value)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n+ *", "\n", text)
    if max_chars:
        text = text[:max_chars]
    return text.strip()
