"""Moteur TTS local avec génération audio streamée et contrôle de prosodie.

Le module fournit:
- des profils de voix (calme, neutre, alerte),
- un mapping état émotionnel -> prosodie,
- un mécanisme de ducking lorsque l'utilisateur parle,
- des bornes strictes sur débit/hauteur/intensité.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import struct
from typing import Iterable, Iterator


class VoiceProfile(str, Enum):
    """Profils de voix disponibles."""

    CALME = "calme"
    NEUTRE = "neutre"
    ALERTE = "alerte"


@dataclass(frozen=True)
class ProsodyBounds:
    """Bornes strictes appliquées à la prosodie finale."""

    min_rate: float = 0.80
    max_rate: float = 1.35
    min_pitch: float = 0.85
    max_pitch: float = 1.25
    min_intensity: float = 0.40
    max_intensity: float = 1.00


@dataclass(frozen=True)
class Prosody:
    """Paramètres prosodiques normalisés."""

    rate: float
    pitch: float
    intensity: float

    def clamp(self, bounds: ProsodyBounds) -> "Prosody":
        """Applique des bornes strictes à chaque dimension prosodique."""

        return Prosody(
            rate=max(bounds.min_rate, min(bounds.max_rate, self.rate)),
            pitch=max(bounds.min_pitch, min(bounds.max_pitch, self.pitch)),
            intensity=max(bounds.min_intensity, min(bounds.max_intensity, self.intensity)),
        )


@dataclass(frozen=True)
class AudioFrame:
    """Bloc audio PCM streamé."""

    pcm_s16le: bytes
    sample_rate_hz: int
    channels: int
    gain: float
    ducked: bool
    prosody: Prosody


_PROFILE_PROSODY: dict[VoiceProfile, Prosody] = {
    VoiceProfile.CALME: Prosody(rate=0.90, pitch=0.92, intensity=0.58),
    VoiceProfile.NEUTRE: Prosody(rate=1.00, pitch=1.00, intensity=0.72),
    VoiceProfile.ALERTE: Prosody(rate=1.16, pitch=1.10, intensity=0.86),
}

# Modulateurs émotionnels additifs (appliqués avant clamp strict).
_EMOTION_DELTAS: dict[str, Prosody] = {
    "neutre": Prosody(rate=0.00, pitch=0.00, intensity=0.00),
    "joie": Prosody(rate=0.08, pitch=0.07, intensity=0.08),
    "enthousiasme": Prosody(rate=0.14, pitch=0.10, intensity=0.12),
    "tristesse": Prosody(rate=-0.10, pitch=-0.08, intensity=-0.12),
    "colere": Prosody(rate=0.10, pitch=-0.02, intensity=0.14),
    "peur": Prosody(rate=0.06, pitch=0.08, intensity=-0.04),
    "fatigue": Prosody(rate=-0.12, pitch=-0.05, intensity=-0.15),
    "calme": Prosody(rate=-0.06, pitch=-0.04, intensity=-0.06),
    "alerte": Prosody(rate=0.12, pitch=0.06, intensity=0.10),
}


class TTSEngine:
    """Moteur TTS simplifié orienté streaming.

    Le rendu audio est volontairement local/synthétique (sinusoïde) pour
    rester testable sans dépendances externes.
    """

    def __init__(
        self,
        *,
        sample_rate_hz: int = 16_000,
        frame_duration_ms: int = 40,
        ducking_gain: float = 0.35,
        bounds: ProsodyBounds | None = None,
    ) -> None:
        self.sample_rate_hz = sample_rate_hz
        self.frame_duration_ms = frame_duration_ms
        self.ducking_gain = ducking_gain
        self.bounds = bounds or ProsodyBounds()

    def prosody_from_state(
        self,
        emotion_state: str,
        voice_profile: VoiceProfile | str = VoiceProfile.NEUTRE,
    ) -> Prosody:
        """Mappe état émotionnel + profil vers une prosodie bornée strictement."""

        profile = VoiceProfile(voice_profile)
        base = _PROFILE_PROSODY[profile]
        delta = _EMOTION_DELTAS.get(emotion_state.lower(), _EMOTION_DELTAS["neutre"])

        merged = Prosody(
            rate=base.rate + delta.rate,
            pitch=base.pitch + delta.pitch,
            intensity=base.intensity + delta.intensity,
        )
        return merged.clamp(self.bounds)

    def generate_stream(
        self,
        text: str,
        *,
        emotion_state: str = "neutre",
        voice_profile: VoiceProfile | str = VoiceProfile.NEUTRE,
        user_speaking: Iterable[bool] | None = None,
    ) -> Iterator[AudioFrame]:
        """Génère un flux de frames audio PCM, avec ducking si l'utilisateur parle."""

        prosody = self.prosody_from_state(emotion_state, voice_profile)
        speech_flags = iter(user_speaking or ())

        samples_per_frame = int(self.sample_rate_hz * (self.frame_duration_ms / 1000.0))
        frame_count = max(1, math.ceil(len(text) / 12))

        for frame_idx in range(frame_count):
            is_user_speaking = next(speech_flags, False)
            gain = self.ducking_gain if is_user_speaking else 1.0
            pcm = self._synthesize_frame(
                text=text,
                frame_idx=frame_idx,
                samples=samples_per_frame,
                prosody=prosody,
                gain=gain,
            )
            yield AudioFrame(
                pcm_s16le=pcm,
                sample_rate_hz=self.sample_rate_hz,
                channels=1,
                gain=gain,
                ducked=is_user_speaking,
                prosody=prosody,
            )

    def _synthesize_frame(
        self,
        *,
        text: str,
        frame_idx: int,
        samples: int,
        prosody: Prosody,
        gain: float,
    ) -> bytes:
        """Synthèse sinusoïdale déterministe, pratique pour tests/unités."""

        checksum = sum(ord(ch) for ch in text) % 40
        base_freq_hz = 170.0 + checksum
        freq = base_freq_hz * prosody.pitch

        # Amplitude bornée en int16.
        amplitude = int(26_000 * prosody.intensity * gain)
        phase_offset = frame_idx * samples

        buf = bytearray()
        for i in range(samples):
            t = (phase_offset + i) / self.sample_rate_hz
            wave = math.sin(2.0 * math.pi * freq * t)
            value = int(max(-32_768, min(32_767, amplitude * wave)))
            buf.extend(struct.pack("<h", value))
        return bytes(buf)
