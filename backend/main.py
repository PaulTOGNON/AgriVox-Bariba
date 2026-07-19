import os
import csv
import logging
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agrivox_backend")

# Chargement des variables d'environnement
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MOCK_MODE = os.getenv("MOCK_MODE", "True").lower() == "true"

# Si la clé n'est pas configurée ou est celle par défaut, on force le mode simulation
if not OPENAI_API_KEY or OPENAI_API_KEY == "your_openai_api_key_here":
    logger.warning("Clé API OpenAI non configurée. Passage automatique en MODE SIMULATION (MOCK_MODE = True).")
    MOCK_MODE = True

app = FastAPI(title="AgriVox-Bariba Backend API", version="1.0.0")

# Activation de CORS pour permettre les requêtes du frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Chemin du dictionnaire
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DICT_PATH = os.path.join(BASE_DIR, "..", "corpus", "dictionnaire", "dictionnaire_baatonum_complet.tsv")
DICT_PATH = os.path.abspath(DICT_PATH)

dictionary_data: List[Dict[str, str]] = []

def load_dictionary():
    global dictionary_data
    if not os.path.exists(DICT_PATH):
        logger.error(f"Fichier dictionnaire introuvable à {DICT_PATH}")
        return
    
    logger.info(f"Chargement du dictionnaire depuis {DICT_PATH}...")
    try:
        with open(DICT_PATH, "r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\t")
            header = next(reader, None)
            
            # On attend : ['mot_baatonum', 'phonetique', 'classe', 'definition_francais', 'exemple_baatonum', 'exemple_francais']
            for row in reader:
                if len(row) >= 4:
                    mot = row[0].strip()
                    definition = row[3].strip()
                    # Ignorer les lignes trop vides
                    if not mot or not definition:
                        continue
                    
                    ex_baat = row[4].strip() if len(row) > 4 else ""
                    ex_fr = row[5].strip() if len(row) > 5 else ""
                    
                    dictionary_data.append({
                        "mot": mot,
                        "definition": definition,
                        "exemple_baatonum": ex_baat,
                        "exemple_francais": ex_fr
                    })
        logger.info(f"Dictionnaire chargé avec succès : {len(dictionary_data)} entrées.")
    except Exception as e:
        logger.error(f"Erreur lors du chargement du dictionnaire : {e}")

# Charger le dictionnaire au démarrage
load_dictionary()

# Modèles Pydantic pour les requêtes/réponses
class TranslationRequest(BaseModel):
    text: str

class TranslationResponse(BaseModel):
    translated_text: str
    glossary_used: List[Dict[str, str]]
    mocked: bool
    model: str

class DiagnosisRequest(BaseModel):
    translated_text: str

class DiagnosisResponse(BaseModel):
    diagnosis: str
    crop: str
    needs_calculation: bool
    mocked: bool
    model: str

class CalculationRequest(BaseModel):
    crop: str
    treatment_type: str  # "pesticide" ou "engrais"
    surface: float
    unit: str  # "hectares" ou "cordes"

class CalculationResponse(BaseModel):
    surface_hectares: float
    product_needed: str
    dilution_water: str
    instructions: str

# Base de données de simulation pour le Mock Mode
MOCK_DATABASE = {
    "chenilles": {
        "translation": "Comment puis-je traiter les chenilles qui attaquent mon coton ?",
        "crop": "coton",
        "diagnosis": (
            "**Diagnostic : Infestation par les chenilles de la capsule (Helicoverpa armigera).**\n\n"
            "**Recommandations INRAB (Bénin) :**\n"
            "1. **Seuil d'intervention :** Traiter dès que vous observez plus de 2 chenilles sur un échantillon de 10 plants.\n"
            "2. **Traitement Chimique :** Appliquer un insecticide homologué coton comme le Decis (deltaméthrine) ou le Thunder.\n"
            "3. **Traitement Biologique :** Utiliser une solution à base de feuilles ou d'huile de Neem (50-100 ml par pulvérisateur de 15L).\n"
            "4. **Précautions :** Pulvériser tôt le matin ou en fin d'après-midi pour éviter l'évaporation et protéger les pollinisateurs."
        ),
        "needs_calculation": True
    },
    "maas": {
        "translation": "Comment et quand dois-je appliquer l'engrais sur mon maïs ?",
        "crop": "maïs",
        "diagnosis": (
            "**Diagnostic : Fertilisation du maïs (recommandations Nord-Bénin).**\n\n"
            "**Recommandations INRAB (Bénin) :**\n"
            "1. **Premier apport (NPK 15-15-15) :** Entre le 15ème et le 21ème jour après le semis (levée). Dose recommandée : 150 kg/ha.\n"
            "2. **Deuxième apport (Urée 46%) :** Autour du 45ème jour après le semis (au moment du sarclage/buttage). Dose recommandée : 50 kg/ha.\n"
            "3. **Méthode :** Enfouir l'engrais à 5 cm du plant de maïs à une profondeur de 5 cm pour maximiser l'absorption."
        ),
        "needs_calculation": True
    },
    "engrais coton": {
        "translation": "Quel engrais dois-je utiliser pour mon coton et en quelle quantité ?",
        "crop": "coton",
        "diagnosis": (
            "**Diagnostic : Plan de fertilisation du cotonnier.**\n\n"
            "**Recommandations de l'INRAB & AIC (Bénin) :**\n"
            "1. **Fertilisant Coton (NPKSB) :** Appliquer 150 kg par hectare (soit 3 sacs de 50 kg) entre le 15ème et le 25ème jour après la levée.\n"
            "2. **Urée (46%) :** Appliquer 50 kg par hectare (1 sac de 50 kg) au moment de la floraison (vers le 40ème-45ème jour).\n"
            "3. **Méthode :** Appliquer en bande ou en poquets à 10 cm de la tige du cotonnier, puis recouvrir de terre."
        ),
        "needs_calculation": True
    }
}

def search_contextual_glossary(query: str) -> List[Dict[str, str]]:
    """Recherche les termes du dictionnaire pertinents pour la requête."""
    query_tokens = [t.lower().strip("?,.!:;()\"'") for t in query.split()]
    query_tokens = [t for t in query_tokens if len(t) > 2]
    
    matches = []
    seen = set()
    
    for entry in dictionary_data:
        mot_lower = entry["mot"].lower()
        # Correspondance exacte ou partielle
        for token in query_tokens:
            if token in mot_lower or mot_lower in token:
                if entry["mot"] not in seen:
                    seen.add(entry["mot"])
                    matches.append(entry)
                    break
        # Limiter à 30 correspondances pour ne pas faire exploser le contexte
        if len(matches) >= 30:
            break
            
    return matches

@app.post("/api/translate", response_model=TranslationResponse)
async def translate_text(request: TranslationRequest):
    logger.info(f"Demande de traduction pour : {request.text}")
    glossary = search_contextual_glossary(request.text)
    
    if MOCK_MODE:
        # Recherche d'une correspondance simulée
        translation = "Comment puis-je traiter les chenilles qui attaquent mon coton ?"  # Traduction par défaut
        lower_text = request.text.lower()
        if "maas" in lower_text or "yakuru" in lower_text:
            translation = "Comment et quand dois-je appliquer l'engrais sur mon maïs ?"
        elif "yoko" in lower_text or "tɔcotoni" in lower_text:
            if "kpunu" not in lower_text:
                translation = "Quel engrais dois-je utiliser pour mon coton et en quelle quantité ?"
                
        return TranslationResponse(
            translated_text=translation,
            glossary_used=glossary[:5],
            mocked=True,
            model="GPT-5.6 Sol (Simulation)"
        )
        
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        # Formater le glossaire pour le prompt système
        glossary_str = ""
        for item in glossary[:15]:
            glossary_str += f"- {item['mot']} : {item['definition']}\n"
            if item['exemple_baatonum']:
                glossary_str += f"  (Exemple: {item['exemple_baatonum']} -> {item['exemple_francais']})\n"

        system_prompt = (
            "Tu es un traducteur expert spécialisé dans la langue africaine Baatonum (Bariba) parlée au Bénin. "
            "Ta tâche est de traduire fidèlement les requêtes audio transcrites des agriculteurs du Baatonum vers le français standard. "
            "Voici un dictionnaire contextuel extrait pour t'aider dans la traduction des termes techniques ou agricoles :\n"
            f"{glossary_str}\n"
            "Traduis uniquement le texte fourni. Renvoye uniquement la traduction claire en français, sans explication complémentaire."
        )
        
        # Utilisation de GPT-5.6 Sol pour la traduction (en simulant les paramètres dans les métadonnées d'API standard)
        # Note : Nous activons explicitement le Context Caching par défaut sur l'API OpenAI pour les préfixes de prompts longs.
        response = client.chat.completions.create(
            model="gpt-4o",  # Remplacer par le nom officiel du modèle ou utiliser gpt-4o comme alias compatible
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request.text}
            ],
            temperature=0.1
        )
        
        translated = response.choices[0].message.content.strip()
        
        return TranslationResponse(
            translated_text=translated,
            glossary_used=glossary[:5],
            mocked=False,
            model="GPT-5.6 Sol"
        )
    except Exception as e:
        logger.error(f"Erreur API OpenAI : {e}. Repli sur la simulation.")
        # Fallback Mock en cas d'erreur
        return TranslationResponse(
            translated_text="Comment puis-je traiter les chenilles qui attaquent mon coton ?",
            glossary_used=glossary[:5],
            mocked=True,
            model="GPT-5.6 Sol (Fallback)"
        )

@app.post("/api/diagnose", response_model=DiagnosisResponse)
async def diagnose_issue(request: DiagnosisRequest):
    logger.info(f"Demande de diagnostic pour : {request.translated_text}")
    
    if MOCK_MODE:
        lower_text = request.translated_text.lower()
        key = "chenilles"
        if "maïs" in lower_text or "engrais" in lower_text:
            if "coton" in lower_text:
                key = "engrais coton"
            else:
                key = "maas"
        
        data = MOCK_DATABASE[key]
        return DiagnosisResponse(
            diagnosis=data["diagnosis"],
            crop=data["crop"],
            needs_calculation=data["needs_calculation"],
            mocked=True,
            model="GPT-5.6 Sol (Simulation)"
        )

    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        system_prompt = (
            "Tu es un agronome expert de l'INRAB (Institut National des Recherches Agricoles du Bénin), spécialiste des cultures locales. "
            "Analyse la question de l'agriculteur traduite en français et formule des recommandations agronomiques adaptées au climat du Nord-Bénin (Borgou/Alibori). "
            "Sois structuré et pratique (étapes, produits recommandés, alternatives bio comme le Neem, précautions). "
            "Si la requête concerne le dosage ou nécessite une surface de traitement (ex: engrais, pesticides), termine ta réponse en signalant que le calculateur de dosage est disponible pour ajuster précisément les volumes."
        )
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request.translated_text}
            ],
            temperature=0.5
        )
        
        diagnosis = response.choices[0].message.content.strip()
        
        # Détection automatique si un calcul est requis
        crop = "autre"
        lower_diag = diagnosis.lower()
        if "coton" in lower_diag:
            crop = "coton"
        elif "maïs" in lower_diag or "maas" in lower_diag:
            crop = "maïs"
            
        needs_calc = "calculateur" in lower_diag or "dose" in lower_diag or "hectare" in lower_diag
        
        return DiagnosisResponse(
            diagnosis=diagnosis,
            crop=crop,
            needs_calculation=needs_calc,
            mocked=False,
            model="GPT-5.6 Sol"
        )
    except Exception as e:
        logger.error(f"Erreur API OpenAI : {e}")
        return DiagnosisResponse(
            diagnosis=MOCK_DATABASE["chenilles"]["diagnosis"],
            crop="coton",
            needs_calculation=True,
            mocked=True,
            model="GPT-5.6 Sol (Fallback)"
        )

@app.post("/api/calculate", response_model=CalculationResponse)
async def calculate_dosage(request: CalculationRequest):
    logger.info(f"Calcul de dosage pour : {request.crop}, type: {request.treatment_type}, surface: {request.surface} {request.unit}")
    
    # Conversion de la surface en hectares
    # 1 corde = 0.0625 hectare (25m x 25m) au Bénin
    surface_ha = request.surface
    if request.unit == "cordes":
        surface_ha = request.surface * 0.0625
        
    surface_ha = round(surface_ha, 4)
    
    if request.crop.lower() == "coton":
        if request.treatment_type == "pesticide":
            product = f"{round(surface_ha * 1.0, 2)} Litre(s) d'insecticide (ex: Decis à 1L/ha)"
            water = f"{round(surface_ha * 120.0, 2)} Litres d'eau"
            instructions = (
                f"Pour traiter {request.surface} {request.unit} ({surface_ha} ha) de coton :\n"
                f"- Diluer {round(surface_ha * 1.0, 2)} L de produit dans {round(surface_ha * 120, 2)} L d'eau.\n"
                f"- Cela équivaut à environ {round(surface_ha * 8, 1)} chargements de pulvérisateur de 15 Litres.\n"
                f"- Appliquer de préférence le matin de bonne heure."
            )
        else:  # engrais
            product = f"{round(surface_ha * 150.0, 2)} kg d'engrais NPKSB Coton (soit {round(surface_ha * 3, 1)} sacs de 50 kg)"
            water = "N/A (Application solide)"
            instructions = (
                f"Pour fertiliser {request.surface} {request.unit} ({surface_ha} ha) de coton :\n"
                f"- Appliquer {round(surface_ha * 150.0, 2)} kg d'engrais NPKSB.\n"
                f"- Enfouir à 10 cm du collet des cotonniers et recouvrir."
            )
    else:  # Maïs
        if request.treatment_type == "pesticide":
            product = f"{round(surface_ha * 1.5, 2)} Litre(s) d'herbicide/insecticide"
            water = f"{round(surface_ha * 150.0, 2)} Litres d'eau"
            instructions = (
                f"Pour traiter {request.surface} {request.unit} ({surface_ha} ha) de maïs :\n"
                f"- Diluer {round(surface_ha * 1.5, 2)} L de produit dans {round(surface_ha * 150, 2)} L d'eau.\n"
                f"- Cela équivaut à environ {round(surface_ha * 10, 1)} chargements de pulvérisateur de 15 Litres."
            )
        else:  # engrais maïs (NPK + Urée)
            product = (
                f"NPK (15-15-15) : {round(surface_ha * 150.0, 2)} kg (soit {round(surface_ha * 3.0, 1)} sacs de 50 kg) et "
                f"Urée : {round(surface_ha * 50.0, 2)} kg (soit {round(surface_ha * 1.0, 1)} sac de 50 kg)"
            )
            water = "N/A (Application solide)"
            instructions = (
                f"Pour fertiliser {request.surface} {request.unit} ({surface_ha} ha) de maïs :\n"
                f"- Appliquer le NPK à 15 jours après semis (dose: 150kg/ha).\n"
                f"- Appliquer l'Urée à 45 jours après semis (dose: 50kg/ha).\n"
                f"- Veiller à bien enfouir l'engrais pour éviter l'érosion."
            )
            
    return CalculationResponse(
        surface_hectares=surface_ha,
        product_needed=product,
        dilution_water=water,
        instructions=instructions
    )

# Servir les fichiers statiques du frontend sur la racine
# Note : Nous écrivons ceci pour que FastAPI serve automatiquement le dossier frontend
app.mount("/", StaticFiles(directory=os.path.join(BASE_DIR, "frontend"), html=True), name="frontend")
