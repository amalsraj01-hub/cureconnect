"""Hand-written condition -> specialist table."""

DEFAULT_SPECIALIST = "General Physician"

DISEASE_TO_SPECIALIST = {
    "(vertigo) Paroymsal  Positional Vertigo": "ENT Specialist",
    "AIDS": "Infectious Disease Specialist",
    "Acne": "Dermatologist",
    "Alcoholic hepatitis": "Gastroenterologist",
    "Allergy": "General Physician",
    "Arthritis": "Orthopedist",
    "Bronchial Asthma": "Pulmonologist",
    "Cervical spondylosis": "Orthopedist",
    "Chicken pox": "General Physician",
    "Chronic cholestasis": "Gastroenterologist",
    "Common Cold": "General Physician",
    "Dengue": "General Physician",
    "Diabetes": "Endocrinologist",
    "Dimorphic hemmorhoids(piles)": "General Surgeon",
    "Drug Reaction": "General Physician",
    "Fungal infection": "Dermatologist",
    "GERD": "Gastroenterologist",
    "Gastroenteritis": "General Physician",
    "Heart attack": "Cardiologist",
    "Hepatitis B": "Gastroenterologist",
    "Hepatitis C": "Gastroenterologist",
    "Hepatitis D": "Gastroenterologist",
    "Hepatitis E": "Gastroenterologist",
    "Hypertension": "General Physician",
    "Hyperthyroidism": "Endocrinologist",
    "Hypoglycemia": "General Physician",
    "Hypothyroidism": "Endocrinologist",
    "Impetigo": "Dermatologist",
    "Jaundice": "Gastroenterologist",
    "Malaria": "General Physician",
    "Migraine": "Neurologist",
    "Osteoarthristis": "Orthopedist",
    "Paralysis (brain hemorrhage)": "Neurologist",
    "Peptic ulcer diseae": "Gastroenterologist",
    "Pneumonia": "Pulmonologist",
    "Psoriasis": "Dermatologist",
    "Tuberculosis": "Pulmonologist",
    "Typhoid": "General Physician",
    "Urinary tract infection": "General Physician",
    "Varicose veins": "Vascular Surgeon",
    "hepatitis A": "Gastroenterologist",
}


def to_specialist(condition: str) -> str:
    return DISEASE_TO_SPECIALIST.get(condition, DEFAULT_SPECIALIST)
