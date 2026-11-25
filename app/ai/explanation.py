"""Optional LLM wording for recommendations. Without OPENAI_API_KEY the rule-based text is used.
The LLM only rephrases the engine's reasons; it never adds game data."""
from __future__ import annotations

import os

import requests

from app.models import ItemRecommendation


def explain(rec: ItemRecommendation, hero_name: str) -> str:
    base = f"{rec.item_name}: {rec.reason}. {rec.benefit}"
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return base
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": os.getenv("DOTASENSE_LLM_MODEL", "gpt-4o-mini"),
                "messages": [
                    {"role": "system", "content": "Rephrase this Dota 2 item advice in 2 short sentences. "
                                                  "Do not add facts that are not in the input."},
                    {"role": "user", "content": f"Hero: {hero_name}. {base}"},
                ],
                "max_tokens": 120,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return base
