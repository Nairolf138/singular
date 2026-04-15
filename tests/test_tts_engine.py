from interaction.tts_engine import ProsodyBounds, TTSEngine, VoiceProfile


def test_prosody_is_strictly_bounded():
    engine = TTSEngine(bounds=ProsodyBounds())

    prosody = engine.prosody_from_state("enthousiasme", VoiceProfile.ALERTE)

    assert 0.80 <= prosody.rate <= 1.35
    assert 0.85 <= prosody.pitch <= 1.25
    assert 0.40 <= prosody.intensity <= 1.00


def test_profiles_shift_baseline_prosody():
    engine = TTSEngine()

    calm = engine.prosody_from_state("neutre", VoiceProfile.CALME)
    neutral = engine.prosody_from_state("neutre", VoiceProfile.NEUTRE)
    alert = engine.prosody_from_state("neutre", VoiceProfile.ALERTE)

    assert calm.rate < neutral.rate < alert.rate
    assert calm.pitch < neutral.pitch < alert.pitch
    assert calm.intensity < neutral.intensity < alert.intensity


def test_generate_stream_applies_ducking_when_user_speaks():
    engine = TTSEngine(ducking_gain=0.25)

    frames = list(
        engine.generate_stream(
            "bonjour tout le monde",
            emotion_state="joie",
            voice_profile=VoiceProfile.NEUTRE,
            user_speaking=[False, True, False],
        )
    )

    assert len(frames) >= 2
    assert frames[0].ducked is False
    assert frames[0].gain == 1.0
    assert frames[1].ducked is True
    assert frames[1].gain == 0.25
    assert len(frames[0].pcm_s16le) > 0
