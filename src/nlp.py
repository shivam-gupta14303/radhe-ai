# nlp.py
"""
NLPManager for Radhe.

Fixes applied vs previous version:
- deep_translator requires a fresh GoogleTranslator(source, target) instance
  per call — the old code passed wrong keyword arg 'target=' to .translate().
- Removed the try/except TypeError workaround; proper API is used directly.

Goal-aligned improvements:
- detect_language() added — useful for Radhe to auto-detect Hindi vs English input.
- Expanded Hindi positive/negative word lists for better bilingual sentiment.
- summarize_text() now trims to max_sentences from ANY position, not just the start,
  by using a simple TF-IDF-style word frequency ranking (no external deps).
"""

import re
import logging
from collections import defaultdict
from typing import List, Dict, Any, Optional

logger = logging.getLogger("Radhe_NLP")
logger.setLevel(logging.INFO)

try:
    from deep_translator import GoogleTranslator
    TRANSLATOR_AVAILABLE = True
except Exception:
    TRANSLATOR_AVAILABLE = False
    logger.warning(
        "deep_translator not available. "
        "Run: pip install deep-translator"
    )

# ── Common stop-words (English + Hindi romanised) ────────────────────
_STOPWORDS = {
    "the","a","an","is","are","was","were","be","been","being",
    "have","has","had","do","does","did","will","would","shall",
    "should","may","might","must","can","could","this","that",
    "these","those","it","its","in","on","at","to","for","of",
    "and","or","but","not","with","from","by","as","about",
    # Hindi romanised
    "hai","hain","ka","ki","ke","ko","se","mein","aur","nahi",
    "kya","tha","the","bhi","yeh","woh","koi","sab",
}


class NLPManager:

    # ==================================================================
    # TRANSLATION
    # ==================================================================

    def translate_text(self, text: str, dest_lang: str = "en") -> str:
        """
        Translate text to dest_lang using deep_translator.

        Fix: deep_translator requires a new GoogleTranslator instance
        with source/target set in the constructor — not in .translate().
        """
        if not text:
            return ""

        if not TRANSLATOR_AVAILABLE:
            logger.warning("Translator not available — returning original text.")
            return text

        try:
            translator = GoogleTranslator(source="auto", target=dest_lang)
            result     = translator.translate(text)
            return result or text

        except Exception as e:
            logger.exception("translate_text failed: %s", e)
            return text

    # ==================================================================
    # LANGUAGE DETECTION
    # ==================================================================

    def detect_language(self, text: str) -> str:
        """
        Simple heuristic to detect if text is primarily Hindi (romanised or Devanagari)
        or English.
        Returns: 'hi', 'en', or 'mixed'
        """
        if not text:
            return "en"

        devanagari = re.findall(r"[\u0900-\u097F]", text)
        if len(devanagari) > 3:
            return "hi"

        hindi_cues = [
            "hai", "hain", "mujhe", "tumhe", "karo", "karna", "bata",
            "aur", "nahi", "kya", "kyun", "kaise", "yahan", "wahan",
            "accha", "theek", "bol", "sun", "dekh",
        ]
        words = text.lower().split()
        hindi_count   = sum(1 for w in words if w in hindi_cues)
        english_count = sum(1 for w in words if re.match(r"^[a-z]+$", w)) - hindi_count

        if hindi_count >= 2 and english_count <= 2:
            return "hi"
        if hindi_count >= 1 and english_count >= 1:
            return "mixed"
        return "en"

    # ==================================================================
    # SENTIMENT
    # ==================================================================

    def detect_sentiment(self, text: str) -> Dict[str, Any]:
        """
        Rule-based bilingual sentiment (English + Hindi romanised + Devanagari cues).
        Returns {sentiment: POSITIVE|NEGATIVE|NEUTRAL, confidence: float}
        """
        if not text:
            return {"sentiment": "NEUTRAL", "confidence": 0.5}

        t = text.lower()

        positive_words = [
            # English
            "good", "great", "excellent", "happy", "joy", "love", "awesome",
            "nice", "amazing", "wonderful", "fantastic", "brilliant", "superb",
            "perfect", "thank", "thanks", "glad", "excited", "best",
            # Hindi romanised
            "accha", "achha", "badiya", "badhiya", "mast", "zabardast",
            "pyaar", "khushi", "shukriya", "wah", "shaandaar",
        ]
        negative_words = [
            # English
            "bad", "terrible", "sad", "angry", "hate", "upset", "awful",
            "worst", "horrible", "frustrated", "annoyed", "boring", "useless",
            "disappointed", "wrong", "error", "failed", "broken",
            # Hindi romanised
            "bura", "buri", "ghatiya", "ganda", "tension", "parishan",
            "gussa", "dukh", "bekar", "faltu", "mushkil", "takleef",
        ]

        pos = sum(1 for w in positive_words if w in t)
        neg = sum(1 for w in negative_words if w in t)

        if pos > neg:
            return {
                "sentiment":  "POSITIVE",
                "confidence": min(0.95, 0.5 + pos * 0.1)
            }
        if neg > pos:
            return {
                "sentiment":  "NEGATIVE",
                "confidence": min(0.95, 0.5 + neg * 0.1)
            }
        return {"sentiment": "NEUTRAL", "confidence": 0.5}

    # ==================================================================
    # KEYWORD EXTRACTION
    # ==================================================================

    def extract_keywords(self, text: str, num_keywords: int = 5) -> List[str]:
        """
        TF-style keyword extraction:
        - Filters stopwords
        - Ranks by frequency
        - Returns top N unique keywords (len > 3)
        """
        if not text:
            return []

        words = re.findall(r"\b[a-zA-Z\u0900-\u097F]{3,}\b", text.lower())
        freq  = defaultdict(int)

        for w in words:
            if w not in _STOPWORDS:
                freq[w] += 1

        ranked = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [w for w, _ in ranked[:num_keywords]]

    # ==================================================================
    # SUMMARISATION
    # ==================================================================

    def summarize_text(
        self,
        text:          str,
        max_sentences: int = 3
    ) -> str:
        """
        Extractive summarisation using word-frequency scoring.

        Improvement over previous version:
        - Scores EVERY sentence by its keyword density, then picks the
          top max_sentences — so important sentences from the middle or end
          are not missed.
        - Falls back to first-N sentences if scoring produces no result.
        """
        if not text:
            return ""

        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+", text)
            if s.strip()
        ]

        if len(sentences) <= max_sentences:
            return text.strip()

        # Build word frequency table
        words = re.findall(r"\b[a-zA-Z\u0900-\u097F]{3,}\b", text.lower())
        freq  = defaultdict(int)
        for w in words:
            if w not in _STOPWORDS:
                freq[w] += 1

        # Score each sentence
        scored = []
        for i, sent in enumerate(sentences):
            sent_words = re.findall(r"\b[a-zA-Z\u0900-\u097F]{3,}\b", sent.lower())
            score      = sum(freq[w] for w in sent_words if w not in _STOPWORDS)
            scored.append((score, i, sent))

        # Pick top sentences, keep original order
        top = sorted(scored, key=lambda x: x[0], reverse=True)[:max_sentences]
        top.sort(key=lambda x: x[1])  # restore document order

        return " ".join(s for _, _, s in top) if top else " ".join(sentences[:max_sentences])


# ── Global instance ───────────────────────────────────────────────────
nlp_manager = NLPManager()