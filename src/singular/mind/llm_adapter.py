"""Adaptateur LLM local avec sortie JSON structurée.

Ce module fournit un client orienté actions pour des modèles locaux (Ollama
ou API compatible) avec :
- prompt système fixe (sécurité + style),
- gestion d'une fenêtre de contexte issue d'une mémoire court terme résumée,
- sorties strictement structurées (JSON intent/action),
- gestion d'erreurs robuste (timeout, retries, fallback modèle).
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any
from urllib import error, request

DEFAULT_SYSTEM_PROMPT = (
    "Tu es un moteur de décision sûr. Respecte strictement les règles suivantes : "
    "(1) refuse toute action dangereuse, illégale, ou violant la confidentialité ; "
    "(2) n'invente pas de faits non présents dans le contexte ; "
    "(3) privilégie des actions minimales, réversibles et explicables ; "
    "(4) réponds uniquement en JSON valide selon le schéma attendu, sans texte libre."
)

_JSON_FORMAT_INSTRUCTION = (
    'Réponds STRICTEMENT avec un objet JSON de la forme: '
    '{"intent": "<string>", "action": {"type": "<string>", "params": {<object>}}, '
    '"reasoning": "<string court>", "confidence": <float entre 0 et 1>}.'
)


class AdapterError(RuntimeError):
    """Erreur de base de l'adaptateur LLM."""


class AdapterTimeoutError(AdapterError):
    """Erreur de timeout lors d'un appel modèle."""


class AdapterResponseError(AdapterError):
    """Erreur de format/réponse du modèle."""


@dataclass(slots=True)
class LLMAdapter:
    """Client local pour produire des décisions JSON structurées."""

    model: str = "llama3.1"
    fallback_model: str = "mistral"
    endpoint: str = "http://localhost:11434/api/generate"
    timeout_s: float = 20.0
    retries: int = 2
    retry_backoff_s: float = 0.6
    memory_window_chars: int = 2_500

    @property
    def system_prompt(self) -> str:
        """Prompt système fixe de sécurité et de style."""

        return DEFAULT_SYSTEM_PROMPT

    def infer(
        self,
        user_input: str,
        short_term_memory: list[str] | None = None,
    ) -> dict[str, Any]:
        """Retourne une action structurée depuis l'entrée utilisateur.

        La méthode tente d'abord le modèle principal, puis le modèle fallback si
        les retries sont épuisés ou si la réponse est invalide.
        """

        memory_summary = self._summarize_short_term_memory(short_term_memory or [])
        prompt = self._build_prompt(user_input=user_input, memory_summary=memory_summary)

        errors: list[Exception] = []
        for model_name in (self.model, self.fallback_model):
            try:
                raw = self._call_with_retries(model_name=model_name, prompt=prompt)
                data = self._extract_json(raw)
                self._validate_action_payload(data)
                data["model_used"] = model_name
                return data
            except Exception as exc:  # noqa: BLE001 - on accumule pour diagnostic
                errors.append(exc)

        joined = " | ".join(f"{type(err).__name__}: {err}" for err in errors)
        raise AdapterError(f"Tous les modèles ont échoué: {joined}")

    def _call_with_retries(self, *, model_name: str, prompt: str) -> str:
        attempts = self.retries + 1
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                return self._call_ollama(model_name=model_name, prompt=prompt)
            except AdapterTimeoutError as exc:
                last_error = exc
            except AdapterResponseError:
                raise
            except Exception as exc:  # noqa: BLE001 - réseau/librairie locale
                last_error = AdapterError(str(exc))

            if attempt < attempts:
                time.sleep(self.retry_backoff_s * attempt)

        assert last_error is not None
        raise last_error

    def _call_ollama(self, *, model_name: str, prompt: str) -> str:
        body = {
            "model": model_name,
            "prompt": prompt,
            "system": self.system_prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
            },
        }
        data = json.dumps(body).encode("utf-8")
        req = request.Request(
            self.endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout_s) as resp:  # nosec B310
                payload = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            raise AdapterResponseError(f"HTTP {exc.code} depuis le serveur local") from exc
        except error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise AdapterTimeoutError(f"Serveur local injoignable/timeout: {reason}") from exc
        except TimeoutError as exc:
            raise AdapterTimeoutError("Timeout appel modèle local") from exc

        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise AdapterResponseError("Réponse brute non-JSON du serveur local") from exc

        response_text = parsed.get("response")
        if not isinstance(response_text, str) or not response_text.strip():
            raise AdapterResponseError("Champ 'response' manquant ou vide dans la réponse API")
        return response_text.strip()

    def _build_prompt(self, *, user_input: str, memory_summary: str) -> str:
        safe_user_input = user_input.strip()
        return (
            f"Contexte mémoire résumé:\n{memory_summary}\n\n"
            f"Entrée utilisateur:\n{safe_user_input}\n\n"
            f"{_JSON_FORMAT_INSTRUCTION}"
        )

    def _summarize_short_term_memory(self, memory_items: list[str]) -> str:
        if not memory_items:
            return "Aucune mémoire court terme disponible."

        normalized = [m.strip() for m in memory_items if m and m.strip()]
        if not normalized:
            return "Aucune mémoire court terme disponible."

        # Stratégie simple, déterministe et sans appel externe: garder les éléments
        # les plus récents avec un budget en caractères.
        kept: list[str] = []
        used = 0
        for item in reversed(normalized):
            chunk = f"- {item}"
            extra = len(chunk) + 1
            if used + extra > self.memory_window_chars:
                break
            kept.append(chunk)
            used += extra

        kept.reverse()
        if not kept:
            tail = normalized[-1][: max(120, self.memory_window_chars - 20)]
            return f"- {tail}"
        return "\n".join(kept)

    def _extract_json(self, raw_text: str) -> dict[str, Any]:
        candidate = raw_text.strip()

        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise AdapterResponseError("Impossible d'extraire un objet JSON valide") from None
            try:
                data = json.loads(candidate[start : end + 1])
            except json.JSONDecodeError as exc:
                raise AdapterResponseError("JSON d'action invalide") from exc

        if not isinstance(data, dict):
            raise AdapterResponseError("La sortie JSON doit être un objet")
        return data

    def _validate_action_payload(self, data: dict[str, Any]) -> None:
        intent = data.get("intent")
        action = data.get("action")
        if not isinstance(intent, str) or not intent.strip():
            raise AdapterResponseError("Champ 'intent' requis (string non vide)")
        if not isinstance(action, dict):
            raise AdapterResponseError("Champ 'action' requis (objet)")

        action_type = action.get("type")
        params = action.get("params")
        if not isinstance(action_type, str) or not action_type.strip():
            raise AdapterResponseError("Champ 'action.type' requis (string non vide)")
        if params is None:
            action["params"] = {}
        elif not isinstance(params, dict):
            raise AdapterResponseError("Champ 'action.params' doit être un objet")

        confidence = data.get("confidence")
        if confidence is not None:
            if not isinstance(confidence, (float, int)):
                raise AdapterResponseError("Champ 'confidence' doit être numérique")
            data["confidence"] = max(0.0, min(1.0, float(confidence)))
