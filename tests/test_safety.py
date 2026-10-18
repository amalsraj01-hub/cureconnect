from app.safety import is_emergency


def test_chest_pain_triggers_emergency():
    assert is_emergency("I have severe chest pain since morning")


def test_breathing_triggers_emergency():
    assert is_emergency("I cannot breathe properly")


def test_new_red_flags_trigger_emergency():
    phrases = [
        "paralysis",
        "sudden weakness",
        "sudden numbness",
        "sudden severe headache",
    ]
    for phrase in phrases:
        assert is_emergency(f"I have {phrase}")


def test_normal_symptom_is_not_emergency():
    assert not is_emergency("I have itchy skin and a small rash")
