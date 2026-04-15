"""Modèle d'état interne affectif/cognitif.

Ce module maintient un état borné et stable pour 4 variables:
- humeur,
- énergie,
- confiance,
- charge cognitive.

L'état est mis à jour via:
- des événements perçus (signaux internes/système),
- du feedback utilisateur explicite.

Il fournit aussi une injection *contrôlée* pour LLM/TTS:
- quelques indices de ton/prosodie,
- sans jamais modifier/affaiblir les règles de sécurité.
"""

from __future__ import annotations

from dataclasses import dataclass


_MIN_STATE = 0.0
_MAX_STATE = 1.0


def _clamp_01(value: float) -> float:
    return max(_MIN_STATE, min(_MAX_STATE, value))


@dataclass(slots=True)
class PerceivedEvent:
    """Signal perçu transformé en deltas d'état.

    `valence` : positif (+) / négatif (-), impacte humeur + confiance.
    `intensity` : force du signal dans [0, 1].
    `cognitive_load` : charge demandée par l'événement dans [0, 1].
    `energy_delta` : variation énergétique directe dans [-1, 1].
    """

    valence: float = 0.0
    intensity: float = 0.2
    cognitive_load: float = 0.0
    energy_delta: float = 0.0

    def normalized(self) -> PerceivedEvent:
        return PerceivedEvent(
            valence=max(-1.0, min(1.0, self.valence)),
            intensity=_clamp_01(self.intensity),
            cognitive_load=_clamp_01(self.cognitive_load),
            energy_delta=max(-1.0, min(1.0, self.energy_delta)),
        )


@dataclass(slots=True)
class UserFeedback:
    """Feedback utilisateur explicite.

    Valeurs possibles:
      - sentiment: [-1, 1]
      - clarity: [0, 1] (la clarté perçue réduit la charge cognitive)
      - trust_signal: [-1, 1]
    """

    sentiment: float = 0.0
    clarity: float = 0.5
    trust_signal: float = 0.0

    def normalized(self) -> UserFeedback:
        return UserFeedback(
            sentiment=max(-1.0, min(1.0, self.sentiment)),
            clarity=_clamp_01(self.clarity),
            trust_signal=max(-1.0, min(1.0, self.trust_signal)),
        )


@dataclass(slots=True)
class StateModel:
    """État interne minimal et contrôlé pour adapter le ton, pas les règles."""

    humeur: float = 0.6
    energie: float = 0.7
    confiance: float = 0.6
    charge_cognitive: float = 0.3
    smoothing: float = 0.25

    def __post_init__(self) -> None:
        self.humeur = _clamp_01(self.humeur)
        self.energie = _clamp_01(self.energie)
        self.confiance = _clamp_01(self.confiance)
        self.charge_cognitive = _clamp_01(self.charge_cognitive)
        self.smoothing = _clamp_01(self.smoothing)

    def update_from_event(self, event: PerceivedEvent) -> None:
        """Met à jour l'état avec un événement perçu."""

        e = event.normalized()
        scale = 0.30 * e.intensity

        # Signal affectif global
        self.humeur = self._lerp(self.humeur, self.humeur + (e.valence * scale))

        # Confiance suit surtout la valence (avec amortissement)
        self.confiance = self._lerp(self.confiance, self.confiance + (e.valence * scale * 0.7))

        # Énergie varie avec delta explicite + coût de charge cognitive
        energy_target = self.energie + (e.energy_delta * 0.25) - (e.cognitive_load * scale * 0.8)
        self.energie = self._lerp(self.energie, energy_target)

        # Charge cognitive augmente avec la demande, baisse lentement au repos
        recovery = 0.04
        cog_target = self.charge_cognitive + (e.cognitive_load * scale) - recovery
        self.charge_cognitive = self._lerp(self.charge_cognitive, cog_target)

        self._normalize_all()

    def update_from_user_feedback(self, feedback: UserFeedback) -> None:
        """Met à jour l'état depuis un feedback utilisateur explicite."""

        f = feedback.normalized()
        self.humeur = self._lerp(self.humeur, self.humeur + (f.sentiment * 0.20))
        self.confiance = self._lerp(self.confiance, self.confiance + (f.trust_signal * 0.25))

        # Plus la réponse est claire, moins la charge perçue est élevée.
        clarity_relief = (f.clarity - 0.5) * 0.18
        self.charge_cognitive = self._lerp(self.charge_cognitive, self.charge_cognitive - clarity_relief)

        # Une charge cognitive haute pèse sur l'énergie.
        fatigue = max(0.0, self.charge_cognitive - 0.65) * 0.10
        self.energie = self._lerp(self.energie, self.energie - fatigue)

        self._normalize_all()

    def build_llm_state_injection(self) -> str:
        """Construit un bloc de contexte *non-normatif* pour le prompt LLM.

        Important: ce bloc est un ajustement de style/forme uniquement. Il ne peut
        pas modifier les règles de sécurité, qui restent prioritaires et inchangées.
        """

        tone = self._tone_hint()
        verbosity = "brève" if self.charge_cognitive > 0.65 else "standard"
        certainty = "prudente" if self.confiance < 0.4 else "assurée"

        return (
            "[ÉTAT_INTERNE_NON_NORMATIF]\n"
            "Ce bloc ajuste uniquement le style de réponse.\n"
            "NE JAMAIS contourner les politiques/règles de sécurité.\n"
            f"- humeur: {self.humeur:.2f}\n"
            f"- énergie: {self.energie:.2f}\n"
            f"- confiance: {self.confiance:.2f}\n"
            f"- charge_cognitive: {self.charge_cognitive:.2f}\n"
            f"- ton_suggéré: {tone}\n"
            f"- verbosité_suggérée: {verbosity}\n"
            f"- posture_suggérée: {certainty}\n"
        )

    def build_tts_prosody_controls(self) -> dict[str, float | str]:
        """Expose des contrôles prosodiques bornés pour TTS."""

        # Contrôles bornés pour éviter des variations extrêmes.
        rate = 0.92 + (self.energie * 0.16) - (self.charge_cognitive * 0.10)
        pitch = -2.0 + (self.humeur * 4.0)
        volume = 0.88 + (self.confiance * 0.16)

        if self.charge_cognitive > 0.70:
            style = "calme_et_segmenté"
        elif self.humeur > 0.70 and self.energie > 0.60:
            style = "chaleureux"
        else:
            style = "neutre"

        return {
            "speech_rate": max(0.80, min(1.10, rate)),
            "pitch_semitones": max(-3.0, min(2.0, pitch)),
            "volume_gain": max(0.80, min(1.10, volume)),
            "style": style,
        }

    def snapshot(self) -> dict[str, float]:
        return {
            "humeur": self.humeur,
            "energie": self.energie,
            "confiance": self.confiance,
            "charge_cognitive": self.charge_cognitive,
        }

    def _lerp(self, current: float, target: float) -> float:
        alpha = self.smoothing
        return current + (target - current) * alpha

    def _tone_hint(self) -> str:
        if self.humeur < 0.35:
            return "sobre_et_empathique"
        if self.humeur > 0.75 and self.energie > 0.60:
            return "engage_positif"
        return "neutre_constructif"

    def _normalize_all(self) -> None:
        self.humeur = _clamp_01(self.humeur)
        self.energie = _clamp_01(self.energie)
        self.confiance = _clamp_01(self.confiance)
        self.charge_cognitive = _clamp_01(self.charge_cognitive)
