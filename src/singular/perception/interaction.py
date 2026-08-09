"""Deterministic, auditable perception of human dialogue."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Mapping

CONTRACT_VERSION = "interaction-signals/1.0"
_WORDS = re.compile(r"[^\W_]+", re.UNICODE)
_NEGATIONS = {
    "aucun",
    "aucune",
    "jamais",
    "ne",
    "non",
    "not",
    "no",
    "never",
    "pas",
    "sans",
}
_INTENSIFIERS = {
    "tres": 1.5,
    "vraiment": 1.4,
    "extremement": 1.8,
    "very": 1.5,
    "really": 1.4,
    "extremely": 1.8,
}
_LEXICON = {
    "frustration": {
        "bug",
        "erreur",
        "error",
        "frustre",
        "frustree",
        "bloque",
        "impossible",
        "nul",
        "fail",
        "failed",
        "wtf",
    },
    "satisfaction": {
        "merci",
        "super",
        "parfait",
        "great",
        "thanks",
        "top",
        "cool",
        "good",
        "bien",
    },
    "urgency": {"urgent", "asap", "vite", "maintenant", "now", "immediat", "deadline"},
}
_THEMES = (
    ("bugfix", {"bug", "erreur", "error", "fix", "incident"}),
    ("performance", {"lent", "slow", "optimisation", "performance", "latence"}),
    ("planning", {"roadmap", "plan", "deadline", "priorite"}),
    ("support", {"help", "aide", "explain", "comprendre"}),
)
_MARKING = {"traumatisant", "traumatic", "critique", "critical", "marquant", "landmark"}


def _normalize(word: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", word.casefold())
        if not unicodedata.combining(c)
    )


def tokenize(text: str) -> list[str]:
    """Return accent-insensitive Unicode words with real word boundaries."""
    return [_normalize(word) for word in _WORDS.findall(text)]


def _load_state(path: Path | None) -> dict[str, float]:
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): float(v) for k, v in data.get("accumulators", {}).items()}
    except (OSError, ValueError, TypeError):
        return {}


def extract_structured_signals(
    text: str, *, state_path: Path | None = None
) -> dict[str, Any]:
    """Observe, interpret and gate dialogue effects without an LLM.

    The returned versioned contract keeps evidence separate from interpretation
    and from the trait deltas that crossed the accumulation threshold.
    """
    word_matches = list(_WORDS.finditer(text))
    tokens = [_normalize(match.group()) for match in word_matches]
    observations: list[dict[str, Any]] = []
    totals = {name: 0.0 for name in _LEXICON}
    for index, token in enumerate(tokens):
        for dimension, vocabulary in _LEXICON.items():
            if token not in vocabulary:
                continue
            start = max(0, index - 3)
            window = tokens[start:index]
            for prior in range(index - 1, start - 1, -1):
                separator = text[
                    word_matches[prior].end() : word_matches[prior + 1].start()
                ]
                if re.search(r"[,;.!?]", separator):
                    window = tokens[prior + 1 : index]
                    break
            negated = any(item in _NEGATIONS for item in window)
            multiplier = max(
                (_INTENSIFIERS.get(item, 1.0) for item in window[-2:]), default=1.0
            )
            weight = 0.0 if negated else multiplier
            totals[dimension] += weight
            observations.append(
                {
                    "token": token,
                    "index": index,
                    "dimension": dimension,
                    "negated": negated,
                    "intensity": multiplier,
                    "source": "human_message",
                }
            )

    scores = {name: round(min(1.0, total * 0.45), 3) for name, total in totals.items()}
    theme = next(
        (
            name
            for name, words in _THEMES
            if any(o["token"] in words and not o["negated"] for o in observations)
        ),
        "general",
    )
    # Themes also use exact normalized tokens, including words not in sentiment lexicons.
    if theme == "general":
        negated_indexes = {int(o["index"]) for o in observations if o["negated"]}
        theme = next(
            (
                name
                for name, words in _THEMES
                if any(
                    token in words and index not in negated_indexes
                    for index, token in enumerate(tokens)
                )
            ),
            "general",
        )
    marking = any(token in _MARKING for token in tokens)
    accumulators = _load_state(state_path)
    deltas: list[dict[str, Any]] = []
    for dimension, trait, direction in (
        ("satisfaction", "optimism", 1.0),
        ("frustration", "resilience", -1.0),
        ("urgency", "patience", -1.0),
    ):
        score = scores[dimension]
        previous = accumulators.get(dimension, 0.0)
        accumulated = max(0.0, previous * 0.8 + (score if score >= 0.3 else 0.0))
        threshold = 0.4 if marking else 1.2
        proposed = direction * (
            0.1 if marking and score >= 0.3 else min(0.04, score * 0.08)
        )
        applied = proposed if accumulated >= threshold else 0.0
        capped = abs(proposed) >= (0.1 if marking else 0.04)
        if applied:
            accumulated = 0.0
        accumulators[dimension] = round(accumulated, 3)
        deltas.append(
            {
                "trait": trait,
                "proposed": round(proposed, 3),
                "applied": round(applied, 3),
                "confidence": score,
                "justification": (
                    "explicit_marking_event"
                    if marking
                    else (
                        "repeated_signal_threshold"
                        if applied
                        else "neutral_zone_or_accumulation_pending"
                    )
                ),
                "source": "interaction_perception",
                "capped": capped,
                "cap": 0.1 if marking else 0.04,
            }
        )
    if state_path is not None:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {"contract_version": CONTRACT_VERSION, "accumulators": accumulators},
                ensure_ascii=False,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    return {
        "contract_version": CONTRACT_VERSION,
        "raw_observations": {
            "text": text,
            "tokens": tokens,
            "matches": observations,
            "source": "human_message",
        },
        "interpretation": {
            **scores,
            "theme": theme,
            "explicitly_marking": marking,
            "accumulators": accumulators,
            "neutral_zone": 0.3,
            "threshold": 0.4 if marking else 1.2,
        },
        "psyche_deltas": deltas,
        # Compatibility fields for consumers of the original unversioned shape.
        **scores,
        "theme": theme,
    }


def apply_psyche_deltas(psyche: object, signals: Mapping[str, Any]) -> None:
    """Apply only audited deltas from the versioned contract, with a final clamp."""
    for delta in signals.get("psyche_deltas", []):
        if not isinstance(delta, Mapping) or not delta.get("applied"):
            continue
        trait = str(delta.get("trait"))
        if hasattr(psyche, trait):
            setattr(
                psyche,
                trait,
                max(
                    0.0,
                    min(1.0, float(getattr(psyche, trait)) + float(delta["applied"])),
                ),
            )
