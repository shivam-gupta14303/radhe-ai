# nlp.py
"""
NLPManager:
- Translation via deep_translator.GoogleTranslator (if available).
- Sentiment detection: simple rule-based with English + some Hindi cues.
- Keyword extraction: frequency-based.
- Summarization: naive first-N-sentences extractive summary.

Used by:
- command_executor.py (for summarize, sentiment, keyword features).
"""

import re
from collections import defaultdict
from typing import List, Dict, Any
import logging

logger = logging.getLogger("Radhe_NLP")
logger.setLevel(logging.INFO)

try:
    from deep_translator import GoogleTranslator
    TRANSLATOR_AVAILABLE = True
except Exception:
    TRANSLATOR_AVAILABLE = False


class NLPManager:
    def __init__(self):
        self.translator = None
        if TRANSLATOR_AVAILABLE:
            try:
                # Default: auto-detect source, target will be given per call.
                self.translator = GoogleTranslator()
            except Exception as e:
                logger.exception("Failed to init GoogleTranslator: %s", e)
                self.translator = None

    def translate_text(self, text: str, dest_lang: str = 'en') -> str:
        """
        Translate text to dest_lang if translator available.
        Otherwise returns original text.
        """
        if not text:
            return ""
        if not self.translator:
            logger.warning("Translator not available; returning original text.")
            return text
        try:
            # deep_translator's GoogleTranslator.translate usually supports target param
            if hasattr(self.translator, "translate"):
                translated = self.translator.translate(text, target=dest_lang)
            else:
                translated = self.translator.translate(text)
            return translated
        except TypeError:
            # try different param name fallback
            try:
                return self.translator.translate(text, dest=dest_lang)
            except Exception as e:
                logger.exception("Translation failed: %s", e)
                return text
        except Exception as e:
            logger.exception("Translation failed: %s", e)
            return text

    def detect_sentiment(self, text: str) -> Dict[str, Any]:
        """
        Very simple rule-based sentiment:
        - checks for some positive/negative English + Hindi words.
        - returns {sentiment: POSITIVE/NEGATIVE/NEUTRAL, confidence: float}
        """
        if not text:
            return {'sentiment': 'NEUTRAL', 'confidence': 0.5}

        t = text.lower()

        positive_words = [
            'good', 'great', 'excellent', 'happy', 'joy', 'love', 'awesome',
            'nice', 'amazing', 'wonderful', 'fantastic',
            'accha', 'achha', 'badiya', 'badhiya', 'mast'
        ]
        negative_words = [
            'bad', 'terrible', 'sad', 'angry', 'hate', 'upset', 'awful',
            'worst', 'horrible',
            'bura', 'buri', 'ghatiya', 'ganda', 'tension', 'parishan', 'tensed'
        ]

        pos = sum(1 for w in positive_words if w in t)
        neg = sum(1 for w in negative_words if w in t)

        if pos > neg:
            return {'sentiment': 'POSITIVE', 'confidence': min(0.9, 0.5 + pos * 0.1)}
        if neg > pos:
            return {'sentiment': 'NEGATIVE', 'confidence': min(0.9, 0.5 + neg * 0.1)}
        return {'sentiment': 'NEUTRAL', 'confidence': 0.5}

    def extract_keywords(self, text: str, num_keywords: int = 5) -> List[str]:
        """
        Very basic keyword extractor: frequency of words longer than 3 chars.
        """
        if not text:
            return []
        words = re.findall(r'\w+', text.lower())
        freq = defaultdict(int)
        for w in words:
            if len(w) > 3:
                freq[w] += 1
        sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [w for w, _ in sorted_words[:num_keywords]]

    def summarize_text(self, text: str, max_sentences: int = 3) -> str:
        """
        Naive sentence splitter using punctuation.
        If text has <= max_sentences sentences, returns original.
        Else returns first max_sentences sentences.
        """
        if not text:
            return ""
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
        if len(sentences) <= max_sentences:
            return text.strip()
        summary = " ".join(sentences[:max_sentences])
        return summary


# global instance
nlp_manager = NLPManager()
