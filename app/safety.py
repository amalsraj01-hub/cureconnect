"""Red-flag checker. If this triggers, skip the ML model entirely."""

RED_FLAGS = [
    "chest pain", "can't breathe", "cannot breathe", "difficulty breathing",
    "trouble breathing", "shortness of breath", "severe bleeding",
    "bleeding heavily", "unconscious", "fainted", "seizure",
    "face drooping", "slurred speech", "suicidal", "want to die",
    "poison", "overdose", "heart attack", "stroke", "paralysis",
    "sudden weakness", "sudden numbness", "sudden severe headache",
]

EMERGENCY_MESSAGE = (
    "This may be an emergency. Call 112 (India) or your local emergency "
    "number, or go to the nearest hospital immediately."
)


def is_emergency(text: str) -> bool:
    t = text.lower()
    return any(flag in t for flag in RED_FLAGS)
