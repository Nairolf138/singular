# Audio perception

Pipeline audio continue qui:

- capture le micro en continu (`MicrophoneCapture`),
- applique un VAD énergétique (`EnergyVAD`) pour début/fin de parole,
- segmente les blocs PCM en buffers de parole (`SegmentBuffer`),
- transcrit localement via Whisper (`WhisperTranscriber`) avec timestamps.

Événements émis:

- `PerceptEvent(event_type="audio_meta")` : volume, bruit, confiance VAD, runtime STT,
- `PerceptEvent(event_type="transcript")` : texte, segments horodatés, confiance, bornes temporelles.

Le transcripteur prévoit un fallback GPU -> CPU (`tiny`) si CUDA indisponible
ou si le chargement du modèle GPU échoue.
