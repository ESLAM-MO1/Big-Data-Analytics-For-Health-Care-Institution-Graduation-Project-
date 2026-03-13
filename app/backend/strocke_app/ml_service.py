import joblib
import tensorflow as tf
import pandas as pd
import numpy as np
from PIL import Image
import os


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_PATH = os.path.join(BASE_DIR, "models")


def dynamic_fusion_v2(clinical_score, image_score=None, patient_data=None):

    contributing_factors = []
    overrides = []

    # STEP 1: Fusion
    if image_score is None:
        fused_score = clinical_score
        fusion_note = "Clinical model only (no imaging available)"
    else:
        w_img = image_score
        w_clin = 1 - image_score
        fused_score = (w_img * image_score) + (w_clin * clinical_score)
        fusion_note = f"Fused: image={w_img:.0%}, clinical={w_clin:.0%}"

    final_score = fused_score
    explanation = fusion_note  # FIX: default value before if-block

    # STEP 2: Rules
    if patient_data:

        bmi = float(patient_data.get("BMI", 0))
        heart = patient_data.get("HeartDisease", "No")
        diabetic = patient_data.get("Diabetic", "No")
        kidney = patient_data.get("KidneyDisease", "No")
        smoking = patient_data.get("Smoking", "No")

        if bmi >= 40:
            final_score = max(final_score, 0.80)
            overrides.append("BMI >= 40")

        if heart == "Yes":
            final_score = max(final_score, 0.75)
            overrides.append("Heart disease")

        if kidney == "Yes":
            final_score = min(final_score + 0.10, 1.0)
            overrides.append("Kidney disease")

        risk_count = sum([
            heart == "Yes",
            diabetic == "Yes",
            smoking == "Yes",
            kidney == "Yes",
            bmi >= 30
        ])

        if risk_count >= 4:
            final_score = max(final_score, 0.85)
            overrides.append("Multiple risk factors")

        # Explainability
        fw = {}

        if image_score is not None:
            fw["Imaging Result"] = round(w_img * image_score, 3)
            fw["Clinical Model"] = round(w_clin * clinical_score, 3)
        else:
            fw["Clinical Model"] = round(clinical_score, 3)

        if heart == "Yes":
            fw["Heart Disease"] = 0.15

        if diabetic == "Yes":
            fw["Diabetes"] = 0.10

        if bmi >= 30:
            fw["High BMI"] = 0.08

        if smoking == "Yes":
            fw["Smoking"] = 0.08

        if kidney == "Yes":
            fw["Kidney Disease"] = 0.10

        total = sum(fw.values())

        contributing_factors = [
            {"factor": k, "weight": round(v / total * 100, 1)}
            for k, v in sorted(fw.items(), key=lambda x: -x[1])
        ]

        top3 = [f["factor"] for f in contributing_factors[:3]]
        explanation = f"Risk driven by: {', '.join(top3)}"

    # STEP 3: Risk Level
    if final_score < 0.40:
        risk_level = "LOW"
        recommendation = "Annual monitoring recommended."

    elif final_score < 0.70:
        risk_level = "MEDIUM"
        recommendation = "Follow-up within 3 months advised."

    else:
        risk_level = "HIGH"
        recommendation = "Immediate neurological evaluation required."

    return {
        "final_score": round(float(final_score), 4),
        "risk_level": risk_level,
        "recommendation": recommendation,
        "fusion_note": fusion_note,
        "overrides_triggered": overrides,
        "explanation": explanation,
        "contributing_factors": contributing_factors
    }


class MLService:

    _clinical_model = None
    _image_model = None
    _fusion_model = None
    _clinical_scaler = None
    _clinical_features = None

    @classmethod
    def load_models(cls):

        if cls._clinical_model is None:
            try:
                cls._clinical_model = joblib.load(os.path.join(MODELS_PATH, "clinical_model_v1.pkl"))
                cls._clinical_scaler = joblib.load(os.path.join(MODELS_PATH, "clinical_scaler_v1.pkl"))
                cls._clinical_features = joblib.load(os.path.join(MODELS_PATH, "clinical_features_v1.pkl"))
                print("✓ Clinical Model loaded successfully")
            except Exception as e:
                print(f"✗ Error loading clinical model: {e}")

        if cls._image_model is None:
            try:
                cls._image_model = tf.keras.models.load_model(
                    os.path.join(MODELS_PATH, "image_model_phase1.keras")
                )
                print("✓ Image Model loaded successfully")
            except Exception as e:
                print(f"✗ Error loading image model: {e}")

        if cls._fusion_model is None:
            try:
                cls._fusion_model = joblib.load(
                    os.path.join(MODELS_PATH, "fusion_model_v1.pkl")
                )
                print("✓ Fusion Model loaded successfully")
            except Exception as e:
                print(f"✗ Error loading fusion model: {e}")

    # ===============================
    # Prepare Clinical Features
    # ===============================
    @classmethod
    def prepare_clinical_features(cls, data):

        bmi = float(data.get('bmi', 0))
        physical_health = int(data.get('physicalhealth', 0))
        mental_health = int(data.get('mentalhealth', 0))
        sleep_time = float(data.get('sleeptime', 0))
        age_num = int(data.get('age', 50))

        is_diabetic = 1 if data.get('diabetic') == 'Yes' else 0
        bad_health = 1 if data.get('genhealth') in ['Poor', 'Fair'] else 0

        risk_score = (
            bmi * 0.02 +
            physical_health * 0.03 +
            mental_health * 0.02 +
            (1 if data.get('heartdisease') == 'Yes' else 0) * 0.3 +
            (1 if data.get('smoking') == 'Yes' else 0) * 0.1
        )

        sex_male = 1 if data.get('sex') == 'Male' else 0
        smoking_yes = 1 if data.get('smoking') == 'Yes' else 0
        alcohol_yes = 1 if data.get('alcoholdrinking') == 'Yes' else 0
        heart_yes = 1 if data.get('heartdisease') == 'Yes' else 0
        diffwalking_yes = 1 if data.get('diffwalking') == 'Yes' else 0

        race = data.get('race', 'White')

        race_asian = 1 if race == 'Asian' else 0
        race_black = 1 if race == 'Black' else 0
        race_hispanic = 1 if race == 'Hispanic' else 0
        race_other = 1 if race == 'Other' else 0
        race_white = 1 if race == 'White' else 0

        physical_activity = 1 if data.get('physicalactivity') == 'Yes' else 0
        asthma = 1 if data.get('asthma') == 'Yes' else 0
        kidney = 1 if data.get('kidneydisease') == 'Yes' else 0

        # FIX: indentation corrected + added return
        features = pd.DataFrame([[
            bmi,
            physical_health,
            mental_health,
            sleep_time,
            age_num,
            is_diabetic,
            bad_health,
            risk_score,
            sex_male,
            smoking_yes,
            alcohol_yes,
            heart_yes,
            diffwalking_yes,
            race_asian,
            race_black,
            race_hispanic,
            race_other,
            race_white,
            physical_activity,
            asthma,
            kidney
        ]], columns=cls._clinical_features)

        return features  # FIX: was missing

    # ===============================
    # Clinical Prediction
    # ===============================
    @classmethod
    def predict_clinical(cls, clinical_data):

        cls.load_models()

        if cls._clinical_model is None:
            raise Exception("Clinical model not loaded")

        features = cls.prepare_clinical_features(clinical_data)

        if cls._clinical_scaler is not None:
            features = cls._clinical_scaler.transform(features)

        try:
            if hasattr(cls._clinical_model, 'predict_proba'):
                score = float(cls._clinical_model.predict_proba(features)[0][1])
            else:
                score = float(cls._clinical_model.predict(features)[0])

            return score

        except Exception as e:
            print(f"Error in clinical prediction: {e}")
            raise

    # ===============================
    # Image Preparation
    # ===============================
    @classmethod
    def prepare_image(cls, image_file):

        try:
            img = Image.open(image_file)

            if img.mode != 'RGB':
                img = img.convert('RGB')

            img = img.resize((224, 224))

            img_array = np.array(img) / 255.0
            img_array = np.expand_dims(img_array, axis=0)

            return img_array

        except Exception as e:
            print(f"Error preparing image: {e}")
            return None

    # ===============================
    # Image Prediction
    # ===============================
    @classmethod
    def predict_image(cls, image_file):

        cls.load_models()

        if cls._image_model is None:
            raise Exception("Image model not loaded")

        img_array = cls.prepare_image(image_file)

        if img_array is None:
            raise Exception("Failed to prepare image")

        try:
            score = float(cls._image_model.predict(img_array)[0][0])
            return score

        except Exception as e:
            print(f"Error in image prediction: {e}")
            raise

    # ===============================
    # Fusion Prediction
    # ===============================
    @classmethod
    def predict_fusion(cls, clinical_score, image_score=None, patient_data=None):

        result = dynamic_fusion_v2(
            clinical_score=clinical_score,
            image_score=image_score,
            patient_data=patient_data
        )

        return result

    # ===============================
    # Risk Level
    # ===============================
    @classmethod
    def determine_risk_level(cls, score):

        if score >= 0.70:
            return 'High'
        elif score >= 0.40:
            return 'Medium'
        else:
            return 'Low'

    # ===============================
    # Recommendation
    # ===============================
    @classmethod
    def get_recommendation(cls, risk_level, clinical_data):

        recommendations = {
            'High': [
                "Immediate medical attention required",
                "Schedule neurologist consultation within 24 hours",
                "Consider hospital admission for observation",
                "Monitor vital signs closely",
                "Order comprehensive stroke panel tests"
            ],
            'Medium': [
                "Schedule follow-up within 1 week",
                "Lifestyle modifications strongly recommended",
                "Consider preventive medication",
                "Monthly health monitoring advised"
            ],
            'Low': [
                "Continue routine health checkups",
                "Maintain healthy lifestyle",
                "Regular exercise recommended",
                "Annual screening advised"
            ]
        }

        return "\n".join(recommendations.get(risk_level, []))

    # ===============================
    # Contributing Factors
    # ===============================
    @classmethod
    def get_contributing_factors(cls, clinical_data, clinical_score):

        factors = []

        if clinical_data.get('heartdisease') == 'Yes':
            factors.append("Heart disease present (High impact)")

        if clinical_data.get('diabetic') == 'Yes':
            factors.append("Diabetic condition (High impact)")

        if clinical_data.get('smoking') in ['Yes', 'Former']:
            factors.append("Smoking history (Medium impact)")

        if float(clinical_data.get('bmi', 0)) > 30:
            factors.append("High BMI - Obesity (Medium impact)")

        if clinical_data.get('kidneydisease') == 'Yes':
            factors.append("Kidney disease (Medium impact)")

        if int(clinical_data.get('physicalhealth', 0)) > 15:
            factors.append("Poor physical health (Low impact)")

        return factors if factors else ["No significant risk factors identified"]


MLService.load_models()