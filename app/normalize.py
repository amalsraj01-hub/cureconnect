"""Translate everyday symptom wording into the dataset's own vocabulary.

The Kaggle data describes symptoms with a fixed list of 131 phrases
("spinning movements", "polyuria", "yellowing of eyes", ...). Real people write
"the room keeps spinning", "i pee a lot", "my eyes turned yellow". The model is
TF-IDF + logistic regression, which only counts word overlap, so if the patient
never types a dataset word the model gets no signal at all.

Three cheap steps, no extra packages:
    1. lowercase, drop punctuation, squeeze whitespace
    2. repair common spelling slips                 (TYPO_MAP)
    3. rewrite everyday phrases as dataset phrases  (SYNONYM_MAP)

app/train.py pushes the training rows through this same function, so training
and prediction speak one language. Nothing here is stored or logged: the text
is cleaned in memory and thrown away, so raw symptom text is never kept.

Rule for adding keys: only add a key when the patient's words do NOT already
exist in the dataset vocabulary. If the dataset already says "cough", there is
no point translating "cough" - and a key that also matches dataset wording adds
words twice (mapping "spinning" -> "spinning movements" would rewrite the
training text "spinning movements" as "spinning movements movements").
tests/test_normalize.py fails if that rule is ever broken.
"""
import re

# --- everyday words -> dataset words --------------------------------------
SYNONYM_MAP = {}

SYNONYM_MAP.update({
    # --- dizziness, balance, vertigo ---
    "vertigo": "spinning movements dizziness",
    "giddiness": "dizziness",
    "giddy": "dizziness",
    "dizzy": "dizziness",
    "dizzy spells": "dizziness spinning movements",
    "light headed": "dizziness",
    "lightheaded": "dizziness",
    "room keeps spinning": "spinning movements",
    "room is spinning": "spinning movements",
    "world is rotating": "spinning movements",
    "whole world is rotating": "spinning movements",
    "everything is spinning": "spinning movements",
    "turning sensation": "spinning movements",
    "spinning sensation": "spinning movements",
    "off balance": "loss of balance unsteadiness",
    "out of balance": "loss of balance unsteadiness",
    "unsteady": "unsteadiness",
    "wobbly": "unsteadiness",
})

SYNONYM_MAP.update({
    # --- yellow eyes / liver / alcohol (hepatitis, jaundice, cholestasis) ---
    "jaundice": "yellowing of eyes yellowish skin",
    "yellow eyes": "yellowing of eyes",
    "eyes look yellow": "yellowing of eyes",
    "eyes turned yellow": "yellowing of eyes",
    "yellow eyed": "yellowing of eyes",
    "eyes are yellow": "yellowing of eyes",
    "yellowish eyes": "yellowing of eyes",
    "yellow skin": "yellowish skin",
    "skin looks yellow": "yellowish skin",
    "skin turned yellowish": "yellowish skin",
    "skin has turned yellowish": "yellowish skin",
    "my liver": "acute liver failure",
    "liver area": "acute liver failure",
    "liver problem": "acute liver failure",
    "liver infection": "acute liver failure",
    "bile": "yellowing of eyes yellowish skin",
    "bile duct": "yellowing of eyes yellowish skin",
    "heavy drinking": "history of alcohol consumption",
    "heavy drinker": "history of alcohol consumption",
    "drinking alcohol": "history of alcohol consumption",
    "drink alcohol": "history of alcohol consumption",
    "drinks daily": "history of alcohol consumption",
    "drink a lot": "history of alcohol consumption",
    "alcohol every day": "history of alcohol consumption",
})

SYNONYM_MAP.update({
    # --- thirst, urination, sugar, hunger, weight (diabetes, UTI) ---
    # The dataset has NO thirst phrase at all, so thirst must borrow a word of
    # Diabetes's own. "polyuria" is the right borrow: it only ever appears in
    # the Diabetes row. The old value was "polyuria excessive hunger", which
    # was wrong twice: it asserted a symptom the patient never reported, and
    # the dataset shares "excessive hunger" with Hyperthyroidism, Hypoglycemia
    # and Migraine, so thirsty sentences were dragged towards those instead of
    # Diabetes. "i pee a lot and i am thirsty" was ranked UTI first at 0.302
    # because of it. See docs/eval_stage5.txt.
    "thirsty": "polyuria",
    "thirst": "polyuria",
    "very thirsty": "polyuria",
    # Same borrow, for thirst phrased without the word. Feeling permanently dry
    # and emptying bottle after bottle is the same complaint the dataset calls
    # nothing at all, so it lands on the one Diabetes-only word. "my mouth stays
    # dry and i finish two bottles of water a day, and i pass a lot of urine"
    # reached no Diabetes word before this and was answered Urinary tract
    # infection at 0.181.
    "always thirsty": "polyuria",
    "constantly thirsty": "polyuria",
    "always feel thirsty": "polyuria",
    "keeps feeling thirsty": "polyuria",
    "dry mouth": "polyuria",
    "mouth stays dry": "polyuria",
    "mouth is always dry": "polyuria",
    "drinking a lot of water": "polyuria",
    "drink a lot of water": "polyuria",
    "drinks a lot of water": "polyuria",
    "drinking lots of water": "polyuria",
    "bottles of water": "polyuria",
    "lots of water every day": "polyuria",
    # Each disease owns one of the two phrases, and the dataset says so plainly:
    # "polyuria" appears in Diabetes rows only (all 120 of them) and
    # "continuous feel of urine" in Urinary tract infection rows only (114 of
    # them). So the borrowing has to follow the meaning of the patient's words.
    # How much or how often urine comes out is the Diabetes sign (polyuria =
    # passing large amounts), so those keys borrow "polyuria".
    #
    # They used to expand to BOTH phrases ("polyuria continuous feel of
    # urine"), which quietly attached a UTI symptom to every sentence that
    # mentioned urinating: "sudden weight loss with extreme hunger and i need to
    # urinate again and again" was answered Urinary tract infection at 0.398
    # with Diabetes down at 0.049. Splitting the borrowing by meaning fixes
    # that: retrained and re-scored over all 125 sentences, top-1 57/125 ->
    # 59/125, specialist-level 88/125 -> 90/125, top-3 unchanged at 94/125, and
    # no sentence lost. See docs/eval_stage6.txt.
    "pee a lot": "polyuria",
    "peeing a lot": "polyuria",
    "urinating a lot": "polyuria",
    "urinate a lot": "polyuria",
    "urinating again and again": "polyuria",
    "urinate again and again": "polyuria",
    "frequent urination": "polyuria",
    "urinating frequently": "polyuria",
    "passing urine frequently": "polyuria",
    "going to the toilet often": "polyuria",
    # "How much" said in everyday words rather than clinical ones, same borrow.
    # "i pass a lot of urine" is literally polyuria, but it was not in the map,
    # so a sentence built around it had no Diabetes evidence whatever.
    "pass a lot of urine": "polyuria",
    "passing a lot of urine": "polyuria",
    "pass lots of urine": "polyuria",
    "passing lots of urine": "polyuria",
    "passing large amounts of urine": "polyuria",
    "large amounts of urine": "polyuria",
    "lots of urine": "polyuria",
    "a lot of urine": "polyuria",
    "pass urine a lot": "polyuria",
    # The urge is the sensation itself rather than an amount, so this is the one
    # urination key that keeps the UTI phrase.
    "frequent urge to urinate": "continuous feel of urine",
    "burning while passing urine": "burning micturition",
    "burning when i urinate": "burning micturition",
    "burning during urination": "burning micturition",
    "burning while urinating": "burning micturition",
    "burning sensation when i pass urine": "burning micturition",
    "pain while passing urine": "burning micturition",
    "urine smells bad": "foul smell of urine",
    "smelly urine": "foul smell of urine",
    "bad smell from urine": "foul smell of urine",
    "cloudy urine": "foul smell of urine",
    "foul smelling urine": "foul smell of urine",
    "blood sugar": "irregular sugar level",
    "blood sugar reading": "irregular sugar level",
    "glucometer": "irregular sugar level",
    "sugar reading": "irregular sugar level",
    "sugar was low": "irregular sugar level",
    "sugar was very low": "irregular sugar level",
    "reading was low": "irregular sugar level",
    "skipped meals": "irregular sugar level",
    "skipping meals": "irregular sugar level",
    "diabetes": "polyuria excessive hunger weight loss irregular sugar level",
    "very hungry": "excessive hunger increased appetite",
    "always hungry": "excessive hunger increased appetite",
    "hungry all the time": "excessive hunger increased appetite",
    "eat a lot": "excessive hunger increased appetite",
    "eating a lot": "excessive hunger increased appetite",
    "losing weight": "weight loss",
    "lost weight": "weight loss",
    "weight is dropping": "weight loss",
    "weight increasing": "weight gain obesity",
    "gaining weight": "weight gain obesity",
    "gained weight": "weight gain obesity",
    "put on weight": "weight gain obesity",
    "wound is not healing": "irregular sugar level fatigue",
    "wound on my foot": "irregular sugar level fatigue",
})

SYNONYM_MAP.update({
    # --- heart, blood pressure, breathing, cough (cardiac, asthma, pneumonia) ---
    "heart beats fast": "fast heart rate palpitations",
    "heart beating fast": "fast heart rate palpitations",
    "fast heartbeat": "fast heart rate palpitations",
    "racing heart": "fast heart rate palpitations",
    "heart pounding": "fast heart rate palpitations",
    "bp": "fast heart rate headache dizziness",
    "blood pressure": "fast heart rate headache dizziness",
    "high bp": "fast heart rate headache dizziness",
    "bp was high": "fast heart rate headache dizziness",
    "bp reading": "fast heart rate headache dizziness",
    "heart attack": "chest pain breathlessness",
    "heaviness in my chest": "chest pain",
    "pressure like pain in my chest": "chest pain",
    "cold sweat": "sweating chest pain",
    "breathless": "breathlessness",
    "feeling breathless": "breathlessness",
    "short of breath": "breathlessness",
    "shortness of breath": "breathlessness",
    "cannot breathe": "breathlessness",
    "difficulty in breathing": "breathlessness",
    "trouble breathing": "breathlessness",
    "breathing difficulty": "breathlessness",
    "getting breathless": "breathlessness",
    "breathless on walking": "breathlessness",
    "wheezing": "breathlessness congestion",
    "wheeze": "breathlessness congestion",
    "whistling sound in my chest": "breathlessness congestion",
    "whistling sound in chest": "breathlessness congestion",
    "chest feels tight": "breathlessness congestion",
    "chest tightness": "breathlessness congestion",
    "tightness in the chest": "breathlessness congestion",
    "tightness in my chest": "breathlessness congestion",
    "tight chest": "breathlessness congestion",
    "inhaler": "breathlessness",
    "mucus": "phlegm mucoid sputum",
    "sticky mucus": "phlegm mucoid sputum",
    "thick mucus": "phlegm mucoid sputum",
    "green phlegm": "phlegm mucoid sputum",
    "green sputum": "phlegm mucoid sputum",
    "greenish sputum": "phlegm mucoid sputum",
    "blood in my cough": "blood in sputum",
    "blood in cough": "blood in sputum",
    "blood stained sputum": "blood in sputum",
    "coughing blood": "blood in sputum",
    "blood mixed sputum": "blood in sputum",
    "chest congestion": "congestion",
    "congested chest": "congestion",
    "cough for more than three weeks": "cough high fever weight loss sweating",
    "long standing cough": "cough weight loss sweating",
    "long lasting cough": "cough weight loss sweating",
    "cough for weeks": "cough weight loss sweating",
})

SYNONYM_MAP.update({
    # --- throat, nose, head, eyes (common cold, sinusitis, migraine) ---
    "sore throat": "throat irritation",
    "throat pain": "throat irritation",
    "throat is sore": "throat irritation",
    "pain in my throat": "throat irritation",
    "blocked nose": "congestion runny nose",
    "nose is blocked": "congestion runny nose",
    "stuffy nose": "congestion runny nose",
    "watery eyes": "watering from eyes",
    "eyes watering": "watering from eyes",
    "watering of eyes": "watering from eyes",
    "red eyes": "redness of eyes",
    "eyes are red": "redness of eyes",
    "head heaviness": "sinus pressure headache",
    "heavy head": "sinus pressure headache",
    "heaviness in my head": "sinus pressure headache",
    "sneezing a lot": "continuous sneezing",
    "constant sneezing": "continuous sneezing",
    "keep sneezing": "continuous sneezing",
    "sneezing and watery eyes": "continuous sneezing watering from eyes",
    "throbbing head": "headache visual disturbances",
    "throbbing headache": "headache visual disturbances",
    "head is pounding": "headache visual disturbances",
    "my head pounds": "headache visual disturbances",
    "pounding in my head": "headache visual disturbances",
    "one sided headache": "headache visual disturbances nausea",
    "one sided throbbing": "headache visual disturbances nausea",
    "head pain": "headache",
    "head ache": "headache",
})

SYNONYM_MAP.update({
    # --- stomach, gut, stool, anus (GERD, ulcers, diarrhoea, piles, hepatitis) ---
    "tummy pain": "stomach pain",
    "tummy ache": "stomach pain",
    "stomach cramps": "stomach pain cramps",
    "cramps in my stomach": "stomach pain cramps",
    "belly cramps": "stomach pain cramps",
    "gnawing pain in the upper belly": "stomach pain indigestion",
    "gastric pain": "stomach pain indigestion",
    "gastric": "stomach pain indigestion",
    "upper abdomen": "abdominal pain",
    "upper belly": "abdominal pain",
    "right upper abdomen": "abdominal pain",
    "loose motions": "diarrhoea",
    "loose motion": "diarrhoea",
    "loose stools": "diarrhoea",
    "watery motions": "diarrhoea",
    "watery stools": "diarrhoea",
    "watery stool": "diarrhoea",
    "passing watery stool": "diarrhoea",
    "vomit": "vomiting",
    "throwing up": "vomiting",
    "threw up": "vomiting",
    "puking": "vomiting",
    "puke": "vomiting",
    "feeling like vomiting": "nausea vomiting",
    "want to vomit": "nausea vomiting",
    "feeling sick": "nausea vomiting",
    "queasy": "nausea vomiting",
    "feeling nauseous": "nausea",
    # Reflux wording belongs to GERD, and GERD's own dataset word for it is
    # "acidity". Twelve of these keys used to expand to "acidity indigestion",
    # but the dataset never pairs "indigestion" with GERD: it appears in Migraine
    # (114 rows) and Peptic ulcer (108) only. So every heartburn sentence was
    # handed a Migraine symptom, and "a hot burning feeling rises behind my
    # breastbone after heavy meals and my mouth fills with sour liquid" was
    # answered Migraine at 0.156 - confident and wrong. Oesophageal wording
    # (heartburn, sour liquid, food coming back up) now borrows "acidity" alone,
    # which is why that sentence drops to Migraine 0.061 and the gate answers
    # "Unclear". GERD cannot rank first there ("acidity" is itself shared, 108
    # GERD rows against 114 Migraine), so "Unclear" is the honest outcome, not a
    # fix to reach for. See docs/eval_stage6.txt.
    "acid reflux": "acidity",
    "reflux": "acidity",
    "heartburn": "acidity",
    "sour water": "acidity",
    "sour taste": "acidity",
    "sour liquid": "acidity",
    "bitter taste": "acidity",
    "food coming back up": "acidity",
    "food comes back": "acidity",
    "regurgitation": "acidity",
    "burning in my chest after eating": "acidity",
    "burning in the chest after eating": "acidity",
    # The two stomach keys keep "indigestion" deliberately: burning *in the
    # stomach* is the dataset's "indigestion" (its word for stomach upset), and
    # dropping it cost a Peptic ulcer sentence its only clue - "burning pain in
    # my stomach before food which gets better after eating" fell from rank 3 to
    # rank 19. The bug was oesophageal wording borrowing a stomach word, not
    # stomach wording using it.
    "burning in my stomach": "acidity indigestion",
    "burning pain in my stomach": "acidity indigestion",
    "gas problem": "passage of gases",
    "gas": "passage of gases",
    "bloating": "distention of abdomen",
    "bloated": "distention of abdomen",
    "abdomen is bloated": "distention of abdomen",
    "stomach is swollen": "swelling of stomach distention of abdomen",
    "swollen stomach": "swelling of stomach distention of abdomen",
    "swelling in my stomach": "swelling of stomach distention of abdomen",
    "black stool": "bloody stool",
    "black coloured stool": "bloody stool",
    "blood in my stool": "bloody stool",
    "blood in stool": "bloody stool",
    "blood on toilet paper": "bloody stool",
    "bleeding while passing stool": "bloody stool",
    "blood while passing stool": "bloody stool",
    "piles": "pain in anal region irritation in anus",
    "hemorrhoids": "pain in anal region irritation in anus",
    "haemorrhoids": "pain in anal region irritation in anus",
    "hemorrhoid": "pain in anal region irritation in anus",
    "pile lumps": "pain in anal region irritation in anus",
    "pile like lumps": "pain in anal region irritation in anus",
    "around my anus": "irritation in anus pain in anal region",
    "near my anus": "irritation in anus pain in anal region",
    "anal area": "irritation in anus",
    "pain while sitting": "pain in anal region",
    "pain when i sit": "pain in anal region",
    "outside food": "diarrhoea vomiting",
    "street food": "diarrhoea vomiting",
    "eating outside": "diarrhoea vomiting",
    "food poisoning": "diarrhoea vomiting",
    "contaminated water": "diarrhoea vomiting",
    "dirty water": "diarrhoea vomiting",
    "unclean water": "diarrhoea vomiting",
    "water contamination": "diarrhoea vomiting",
})

SYNONYM_MAP.update({
    # --- skin, hair, nails, veins, legs (fungal, acne, psoriasis, varicose) ---
    "itchy": "itching",
    "itches": "itching",
    "itch": "itching",
    "itchiness": "itching",
    "burning skin": "itching skin rash",
    "skin burns": "itching skin rash",
    "red patches": "skin rash",
    "itchy patches": "skin rash itching",
    "skin patches": "skin rash",
    "red itchy patches": "skin rash itching",
    "thick patches": "silver like dusting skin peeling",
    "ring shaped": "dischromic patches skin rash",
    "ring shaped patches": "dischromic patches skin rash",
    "ring like patches": "dischromic patches skin rash",
    "scaly": "silver like dusting skin peeling",
    "scales": "silver like dusting skin peeling",
    "flakes": "silver like dusting skin peeling",
    "flaking": "silver like dusting skin peeling",
    "silvery": "silver like dusting skin peeling",
    "silver scales": "silver like dusting skin peeling",
    "skin coming off": "silver like dusting skin peeling",
    "skin flakes": "silver like dusting skin peeling",
    "scalp": "silver like dusting skin peeling",
    "dandruff": "silver like dusting skin peeling",
    "fungal": "itching skin rash nodal skin eruptions",
    "fungus": "itching skin rash nodal skin eruptions",
    "fungal infection": "itching skin rash nodal skin eruptions",
    "groin": "itching skin rash",
    "inner thigh": "itching skin rash",
    "between my legs": "itching skin rash",
    "between my toes": "skin peeling itching",
    "toes": "skin peeling itching",
    "nails look thick": "brittle nails inflammatory nails",
    "thick nails": "brittle nails inflammatory nails",
    "yellow nails": "brittle nails inflammatory nails",
    "nail infection": "brittle nails inflammatory nails",
    "acne": "blackheads pus filled pimples",
    "boils": "pus filled pimples",
    "boils and pimples": "pus filled pimples blackheads",
    "pimples and blackheads": "blackheads pus filled pimples",
    "zits": "pus filled pimples",
    "oily skin": "blackheads pus filled pimples",
    "sores": "red sore around nose blister",
    "red sores": "red sore around nose blister",
    "crusted sores": "red sore around nose blister",
    "crusted": "red sore around nose blister",
    "sore around my nose": "red sore around nose",
    "sores around the nose": "red sore around nose",
    "honey coloured crust": "yellow crust ooze",
    "oozing": "yellow crust ooze",
    "oozed": "yellow crust ooze",
    "blisters": "blister",
    "fluid filled blisters": "blister",
    "spots on my legs": "red spots over body",
    "spots on the body": "red spots over body",
    "spots appeared": "red spots over body",
    "rash with spots": "red spots over body skin rash",
    "mouth ulcers": "ulcers on tongue",
    "ulcers in my mouth": "ulcers on tongue",
    "ulcers in the mouth": "ulcers on tongue",
    "sores in my mouth": "ulcers on tongue",
    "white patches in my mouth": "patches in throat",
    "patches in my mouth": "patches in throat",
    "white patches inside my mouth": "patches in throat",
    "patches in my throat": "patches in throat",
    "swollen lips": "swollen extremeties",
    "lips swelled": "swollen extremeties",
    "my lips swelled up": "swollen extremeties",
    "swelling on my lips": "swollen extremeties",
    "swelling of my face": "swollen extremeties",
    "face swelled": "swollen extremeties",
    "face is puffy": "puffy face and eyes",
    "puffy eyes": "puffy face and eyes",
    "swollen glands": "swelled lymph nodes",
    "glands are swollen": "swelled lymph nodes",
    "legs are swollen": "swollen legs",
    "swelling in my legs": "swollen legs",
    "swollen ankle": "swollen legs",
    "ankle is swollen": "swollen legs",
    "swollen feet": "swollen legs",
    "blue veins": "prominent veins on calf swollen blood vessels",
    "bulging veins": "prominent veins on calf swollen blood vessels",
    "bulging blue veins": "prominent veins on calf swollen blood vessels",
    "twisted veins": "prominent veins on calf swollen blood vessels",
    "visible veins": "prominent veins on calf swollen blood vessels",
    "veins like worms": "prominent veins on calf swollen blood vessels",
    "varicose": "prominent veins on calf swollen blood vessels",
    "leg cramps": "cramps",
    "cramps in my legs": "cramps",
    "leg pain": "cramps",
    "pain in my legs": "cramps",
    "heavy legs": "cramps",
    "legs feel heavy": "cramps",
})

SYNONYM_MAP.update({
    # --- tiredness, concentration (thyroid, anaemia, diabetes, depression) ---
    "tired": "fatigue lethargy",
    "tiredness": "fatigue lethargy",
    "very tired": "fatigue lethargy",
    "always tired": "fatigue lethargy",
    "exhausted": "fatigue lethargy",
    "weak": "fatigue lethargy",
    "very weak": "fatigue lethargy",
    "no energy": "fatigue lethargy",
    "drowsy": "lethargy",
    "sleepy": "lethargy",
    "slow thinking": "lethargy lack of concentration",
    "cannot concentrate": "lack of concentration",
    "no concentration": "lack of concentration",
    "pale": "fatigue",
    "pale face": "fatigue",
    "cannot sleep": "restlessness",
    "sleepless": "restlessness",
    "no sleep": "restlessness",
    "anxious all the time": "anxiety restlessness",
})

SYNONYM_MAP.update({
    # --- one-sided weakness, numbness, speech (paralysis, stroke) ---
    "numbness": "weakness in limbs",
    "tingling in fingers": "weakness in limbs",
    "tingling in my fingers": "weakness in limbs",
    "tingling fingers": "weakness in limbs",
    "tingling and numbness": "weakness in limbs",
    "numbness in fingers": "weakness in limbs",
    "fingers feel numb": "weakness in limbs",
    "numb in my hands": "weakness in limbs",
    "weakness on the right side": "weakness of one body side",
    "weakness on the left side": "weakness of one body side",
    "right side of my body": "weakness of one body side",
    "left side of my body": "weakness of one body side",
    "one side of my body": "weakness of one body side",
    "one side of the body": "weakness of one body side",
    "one side of his mouth": "weakness of one body side",
    "one side of his face": "weakness of one body side",
    "mouth is drooping": "weakness of one body side",
    "face drooping": "weakness of one body side",
    "drooping": "weakness of one body side",
    "cannot lift my arm": "weakness in limbs",
    "cannot lift his arm": "weakness in limbs",
    "cannot lift my left arm": "weakness in limbs",
    "cannot lift his left arm": "weakness in limbs",
    "unable to speak": "slurred speech weakness of one body side",
    "cannot speak": "slurred speech weakness of one body side",
    "speech became slurred": "slurred speech",
    "paralysis": "weakness of one body side weakness in limbs",
    "stroke": "weakness of one body side slurred speech",
    "brain hemorrhage": "weakness of one body side slurred speech",
})

SYNONYM_MAP.update({
    # --- thyroid and hormones ---
    "thyroid is low": "enlarged thyroid",
    "thyroid problem": "enlarged thyroid",
    "checked my thyroid": "enlarged thyroid",
    "thyroid test": "enlarged thyroid",
    "my thyroid": "enlarged thyroid",
    "hypothyroid": "enlarged thyroid weight gain",
    "hyperthyroid": "enlarged thyroid fast heart rate weight loss",
    "bulging eyes": "enlarged thyroid fast heart rate",
    "always cold": "cold hands and feets",
    "feel cold": "cold hands and feets",
    "feeling cold": "cold hands and feets",
    "cold all the time": "cold hands and feets",
    "heavy periods": "abnormal menstruation",
    "periods are heavy": "abnormal menstruation",
    "irregular periods": "abnormal menstruation",
    "before my periods": "abnormal menstruation",
})

SYNONYM_MAP.update({
    # --- naming a disease out loud (people often say the name they were told) ---
    # We cannot output the label from the input, so we translate the name into
    # the symptom signature that disease has in the dataset instead.
    "dengue": "high fever pain behind the eyes red spots over body",
    "malaria": "high fever chills shivering sweating",
    "typhoid": "high fever abdominal pain constipation",
    "tuberculosis": "cough high fever weight loss sweating blood in sputum",
    "tb": "cough weight loss sweating blood in sputum",
    "pneumonia": "cough high fever breathlessness phlegm chest pain",
    "hepatitis": "yellowing of eyes yellowish skin dark urine",
    "common cold": "runny nose congestion throat irritation continuous sneezing",
    "gastro": "diarrhoea vomiting stomach pain",
    "migraine": "headache visual disturbances nausea vomiting",
    "arthritis": "joint pain movement stiffness swelling joints",
    "psoriasis": "silver like dusting skin peeling itching",
    "impetigo": "red sore around nose yellow crust ooze",
    "allergy": "continuous sneezing watering from eyes itching",
    "chicken pox": "blister skin rash itching high fever",
})

SYNONYM_MAP.update({
    # --- how it was caught / what triggered it (risk factors and allergies) ---
    "mosquito": "high fever red spots over body",
    "mosquito bite": "high fever red spots over body",
    "mosquito bites": "high fever red spots over body",
    "platelet count": "red spots over body high fever",
    "platelets": "red spots over body high fever",
    "unprotected contact": "extra marital contacts",
    "unprotected sex": "extra marital contacts",
    "unprotected": "extra marital contacts",
    "immunity": "muscle wasting patches in throat",
    "low immunity": "muscle wasting patches in throat",
    "my immunity is very low": "muscle wasting patches in throat",
    "new tablet": "itching skin rash",
    "new medicine": "itching skin rash",
    "antibiotic": "itching skin rash",
    "after taking a medicine": "itching skin rash",
    "after taking the new tablet": "itching skin rash",
    "prawns": "continuous sneezing watering from eyes itching",
    "shellfish": "continuous sneezing watering from eyes itching",
    "pollen": "continuous sneezing watering from eyes itching",
    "dust": "continuous sneezing watering from eyes itching",
    "nuts": "continuous sneezing watering from eyes itching",
})

# === end of synonym map ===
TYPO_MAP = {
    # spelling slips and alternate spellings seen in real typing
    "vomitng": "vomiting",
    "vomitting": "vomiting",
    "vomting": "vomiting",
    "giddines": "dizziness",
    "dizzines": "dizziness",
    "dizy": "dizziness",
    "headake": "headache",
    "hedache": "headache",
    "headche": "headache",
    "stomack": "stomach",
    "stomache": "stomach",
    "stomch": "stomach",
    "feaver": "fever",
    "fevor": "fever",
    "tempriture": "temperature",
    "muscel": "muscle",
    "muscels": "muscle",
    "jont": "joint",
    "cheaks": "cheeks",
    "yesterdy": "yesterday",
    "diarea": "diarrhoea",
    "diahrea": "diarrhoea",
    "diarhea": "diarrhoea",
    "diarrhea": "diarrhoea",
    "brething": "breathing",
    "thyriod": "thyroid",
    "bleading": "bleeding",
    "caugh": "cough",
    "coughin": "coughing",
    "migrain": "migraine",
    "artheritis": "arthritis",
    "jaundise": "jaundice",
    "presure": "pressure",
    "sweling": "swelling",
    "freqency": "frequency",
    "painfull": "painful",
    "thristy": "thirsty",
    "tierd": "tired",
    "anixety": "anxiety",
    "depresion": "depression",
    "constpation": "constipation",
    "indegestion": "indigestion",
    "inhalor": "inhaler",
    "medicin": "medicine",
    "medecine": "medicine",
    "suger": "sugar",
    "diebetes": "diabetes",
    "diabeties": "diabetes",
    "sezure": "seizure",
}


def _compile(mapping):
    """One regex matching any key, longest first so phrases beat single words."""
    keys = sorted(mapping, key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(re.escape(key) for key in keys) + r")\b")


def _apply(text, pattern, mapping):
    """Replace every match in one single pass (output is never re-scanned)."""
    return pattern.sub(lambda match: mapping[match.group(0)], text)


TYPO_PATTERN = _compile(TYPO_MAP)
SYNONYM_PATTERN = _compile(SYNONYM_MAP)
PUNCTUATION_PATTERN = re.compile(r"[^\w\s]+")


def normalize(text: str) -> str:
    """Lowercase, repair typos and translate everyday words to dataset words."""
    text = PUNCTUATION_PATTERN.sub(" ", str(text).lower())
    text = _apply(text, TYPO_PATTERN, TYPO_MAP)
    text = _apply(text, SYNONYM_PATTERN, SYNONYM_MAP)
    return " ".join(text.split())
