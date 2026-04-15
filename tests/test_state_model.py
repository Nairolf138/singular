from mind.state_model import PerceivedEvent, StateModel, UserFeedback


def test_state_model_event_updates_are_bounded() -> None:
    state = StateModel(humeur=0.5, energie=0.5, confiance=0.5, charge_cognitive=0.2)

    event = PerceivedEvent(valence=1.0, intensity=1.0, cognitive_load=0.9, energy_delta=-0.8)
    state.update_from_event(event)

    snap = state.snapshot()
    assert set(snap) == {"humeur", "energie", "confiance", "charge_cognitive"}
    assert all(0.0 <= v <= 1.0 for v in snap.values())


def test_user_feedback_lowers_cognitive_load_when_clear() -> None:
    state = StateModel(charge_cognitive=0.7)

    state.update_from_user_feedback(UserFeedback(sentiment=0.2, clarity=1.0, trust_signal=0.1))

    assert state.charge_cognitive < 0.7


def test_llm_injection_keeps_safety_priority_message() -> None:
    state = StateModel()

    text = state.build_llm_state_injection()

    assert "NE JAMAIS contourner les politiques/règles de sécurité" in text


def test_tts_controls_are_bounded() -> None:
    state = StateModel(humeur=1.0, energie=1.0, confiance=1.0, charge_cognitive=0.0)

    controls = state.build_tts_prosody_controls()

    assert 0.80 <= float(controls["speech_rate"]) <= 1.10
    assert -3.0 <= float(controls["pitch_semitones"]) <= 2.0
    assert 0.80 <= float(controls["volume_gain"]) <= 1.10
    assert controls["style"] in {"calme_et_segmenté", "chaleureux", "neutre"}
