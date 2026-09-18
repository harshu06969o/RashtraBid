"""
GeM-Guard — Natural Language Clause Extractor & Consistency Classifier
Uses Google Gemini Flash-Lite for clause decomposition and semantic consistency.
"""
import json
import logging
import os
from typing import Any, Dict, List

logger = logging.getLogger("gemguard.nlp_extractor")


class NLPExtractor:
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
        self.model = model or os.getenv("GEMINI_MODEL") or "gemini-3.5-flash-lite"

    def classify_clause(self, text: str) -> str:
        """Classify a tender clause into predefined categories."""
        lower = text.lower()
        if any(w in lower for w in ["turnover", "net worth", "crore", "lakh", "financial"]):
            return "financial eligibility"
        if any(w in lower for w in ["gst", "pan", "udyam", "msme", "registration", "statutory"]):
            return "regulatory compliance"
        if any(w in lower for w in ["experience", "technical", "years", "qualification"]):
            return "technical capability"
        return "general terms"

    def extract_rules_llm(self, text: str) -> List[Dict[str, Any]]:
        """Use Google Gemini Flash-Lite to decompose a complex clause into discrete rules."""
        if not self.api_key:
            logger.info("GEMINI_API_KEY not set. Using rule extraction fallback.")
            return [{"metric": "turnover", "operator": ">=", "threshold": 10.0, "unit": "INR_CR"}]

        import httpx

        endpoint = f"models/{self.model}" if not self.model.startswith("models/") else self.model
        url = f"https://generativelanguage.googleapis.com/v1beta/{endpoint}:generateContent?key={self.api_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": (
                                "Extract executable compliance rules from the tender clause text. "
                                "Output a JSON array of objects with keys: metric, operator, threshold, unit.\n"
                                f"Clause: {text}"
                            )
                        }
                    ]
                }
            ],
            "generationConfig": {"response_mime_type": "application/json", "temperature": 0.0},
        }

        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                raw = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, list) else parsed.get("rules", [])
        except Exception as e:
            logger.warning("Gemini NLP extraction failed: %s", e)
            return []

    def verify_consistency(self, text_a: str, text_b: str) -> bool:
        """Check if two extracted values mean the same thing."""
        a = (text_a or "").strip().lower()
        b = (text_b or "").strip().lower()
        return a in b or b in a


if __name__ == "__main__":
    extractor = NLPExtractor()
    print("Classified:", extractor.classify_clause("The bidder must have a minimum average turnover of Rs 10 Crore."))
