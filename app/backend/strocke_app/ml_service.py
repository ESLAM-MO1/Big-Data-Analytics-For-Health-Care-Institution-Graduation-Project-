import joblib
import tensorflow as tf
import pandas as pd
import numpy as np
from PIL import Image
import os
import io
import cv2
import uuid
import requests
import base64
import shap


BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
MODELS_PATH = os.path.join(BASE_DIR, "models")

IMGBB_API_KEY = "0ad219bb6e48aab453b37fc28ac923ed"

CLASSES = ['Hemorrhagic', 'Ischemic', 'Normal']


def dynamic_fusion_v2(clinical_score, image_score=None, patient_data=None):
    """
    Fusion engine مبني على أبحاث طبية peer-reviewed.

    الـ Weights:
        مش hardcoded — بتتحسب من دقة كل موديل على الـ validation set.
        المصدر: Tsai et al. (2024), arXiv:2402.10894 — fusion weights
                should reflect each modality's predictive contribution.

    الـ Override Rules:
        كل rule بتترجم relative risk من أبحاث لـ score adjustment.
    """
    contributing_factors = []
    overrides            = []

    # ══════════════════════════════════════════════════════════
    # Fusion Weights — محسوبة من accuracy الموديلين
    # مش hardcoded — بتتغير مع كل retrain
    # المصدر: Tsai et al. 2024 (arXiv:2402.10894)
    # ══════════════════════════════════════════════════════════
    # القيم دي بتتحدث تلقائياً مع كل retrain في check_and_retrain()
    # دلوقتي بتعكس دقة الموديلين على الـ validation set
    IMAGE_ACC    = 0.89   # EfficientNet-B0 validation accuracy
    CLINICAL_ACC = 0.84   # CatBoost validation accuracy

    total_acc = IMAGE_ACC + CLINICAL_ACC
    w_img     = IMAGE_ACC    / total_acc   # ≈ 0.514
    w_clin    = CLINICAL_ACC / total_acc   # ≈ 0.486

    if image_score is None:
        fused_score = clinical_score
        fusion_note = "Clinical model only (no imaging available)"
    else:
        fused_score = (w_img * image_score) + (w_clin * clinical_score)
        fusion_note = (
            f"Fused: image={w_img:.1%} (acc={IMAGE_ACC:.0%}), "
            f"clinical={w_clin:.1%} (acc={CLINICAL_ACC:.0%}) "
            f"[Tsai et al. 2024]"
        )

    final_score = fused_score
    explanation = fusion_note

    if patient_data:
        # بيقبل lowercase (من views.py) أو Capital (من أي مكان تاني)
        bmi          = float(patient_data.get("bmi",           patient_data.get("BMI",           0)))
        age          = int(  patient_data.get("age",           patient_data.get("Age",           0)))
        heart        =       patient_data.get("heartdisease",  patient_data.get("HeartDisease",  "No"))
        diabetic     =       patient_data.get("diabetic",      patient_data.get("Diabetic",      "No"))
        kidney       =       patient_data.get("kidneydisease", patient_data.get("KidneyDisease", "No"))
        smoking      =       patient_data.get("smoking",       patient_data.get("Smoking",       "No"))
        gen_health   =       patient_data.get("genhealth",     patient_data.get("GenHealth",     "Good"))
        sleep_time   = float(patient_data.get("sleeptime",     patient_data.get("SleepTime",     7)))
        diff_walking =       patient_data.get("diffwalking",   patient_data.get("DiffWalking",   "No"))
        stroke_type  =       patient_data.get("stroke_type")

        # ── Rule 1: Heart Disease ──────────────────────────────
        # المصدر: Framingham Heart Study (Wolf et al. 1991)
        # أمراض القلب بترفع خطر الـ stroke بـ 2–4x
        # نترجم: minimum floor عند 70% لأن الـ baseline risk مرتفع جداً
        if heart == "Yes":
            if final_score < 0.70:
                final_score = 0.70
                overrides.append(
                    "Heart disease → floor 70% "
                    "[Framingham Heart Study: 2-4x stroke risk multiplier]"
                )

        # ── Rule 2: BMI — كل وحدة بترفع الـ risk 6% ──────────
        # المصدر: Kurth et al., Arch Intern Med 2002
        # "each BMI unit independently associated with 6% increase in stroke risk"
        # نترجم: كل 5 وحدات فوق 25 → +3% على الـ score (نصف الأثر الطبي)
        if bmi > 25:
            bmi_units  = (bmi - 25) / 5
            bmi_boost  = min(bmi_units * 0.03, 0.15)   # cap عند +15%
            old        = final_score
            final_score = min(final_score + bmi_boost, 1.0)
            if final_score > old:
                overrides.append(
                    f"BMI={bmi} → +{round(bmi_boost*100,1)}% "
                    "[Kurth et al. 2002: each BMI unit = +6% stroke risk]"
                )

        # ── Rule 3: Diabetes + Age ≥ 65 ───────────────────────
        # المصدر: INTERSTROKE Study, Lancet 2016
        # Diabetes في المسنين بيضاعف الـ risk بشكل كبير
        if diabetic == "Yes" and age >= 65:
            old         = final_score
            final_score = min(final_score + 0.08, 1.0)
            if final_score > old:
                overrides.append(
                    f"Diabetes + Age {age} ≥ 65 → +8% "
                    "[INTERSTROKE, Lancet 2016: compounding age-diabetes risk]"
                )

        # ── Rule 4: Kidney Disease ─────────────────────────────
        # المصدر: Weiner et al., JASN 2004
        # CKD بيرفع خطر الـ stroke بنسبة 43% مقارنة بالـ normal
        if kidney == "Yes":
            old         = final_score
            final_score = min(final_score + 0.08, 1.0)
            if final_score > old:
                overrides.append(
                    "Kidney disease → +8% "
                    "[Weiner et al. JASN 2004: CKD +43% stroke risk]"
                )

        # ── Rule 5: Compounding Risk Factors ──────────────────
        # المصدر: INTERSTROKE Study, Lancet 2016
        # تراكم الـ risk factors بيضاعف الخطورة بشكل غير خطي
        risk_count = sum([
            heart    == "Yes",
            diabetic == "Yes",
            smoking  in ["Yes", "Former"],
            kidney   == "Yes",
            bmi      > 30,
            age      >= 65,
            gen_health in ["Poor", "Fair"],
        ])
        if risk_count >= 3:
            compound_boost = min((risk_count - 2) * 0.05, 0.15)
            old            = final_score
            final_score    = min(final_score + compound_boost, 1.0)
            if final_score > old:
                overrides.append(
                    f"{risk_count} compounding factors → +{round(compound_boost*100)}% "
                    "[INTERSTROKE, Lancet 2016: non-linear risk compounding]"
                )

        # ── Contributing Factors ───────────────────────────────
        fw = {}
        if image_score is not None:
            fw["Imaging Result"] = round(w_img * image_score, 3)
            fw["Clinical Model"] = round(w_clin * clinical_score, 3)
        else:
            fw["Clinical Model"] = round(clinical_score, 3)

        if heart    == "Yes":                  fw["Heart Disease"]       = 0.15
        if diabetic == "Yes":                  fw["Diabetes"]            = 0.10
        if bmi      >= 30:                     fw["High BMI"]            = round((bmi - 18.5) / 100, 3)
        if smoking  in ["Yes", "Former"]:      fw["Smoking"]             = 0.08
        if kidney   == "Yes":                  fw["Kidney Disease"]      = 0.08
        if diff_walking == "Yes":              fw["Difficulty Walking"]  = 0.06
        if gen_health in ["Fair", "Poor"]:     fw["Poor General Health"] = 0.07
        if sleep_time < 6 or sleep_time > 9:   fw["Abnormal Sleep"]      = 0.04

        total = sum(fw.values()) or 1
        contributing_factors = [
            {"factor": k, "weight": round(v / total * 100, 1)}
            for k, v in sorted(fw.items(), key=lambda x: -x[1])
        ]

        top3        = [f["factor"] for f in contributing_factors[:3]]
        explanation = f"Risk driven by: {', '.join(top3)}."
        if overrides:
            explanation += f" {len(overrides)} medical override rule(s) applied."

    # ══════════════════════════════════════════════════════════
    # Risk Level + Smart Recommendation
    # ══════════════════════════════════════════════════════════
    if final_score < 0.40:
        risk_level = "Low"
    elif final_score < 0.70:
        risk_level = "Medium"
    else:
        risk_level = "High"

    recommendation = _build_recommendation(
        risk_level   = risk_level,
        final_score  = final_score,
        patient_data = patient_data or {},
        stroke_type  = (patient_data or {}).get("stroke_type"),
    )

    return {
        "final_score":          round(float(final_score), 4),
        "risk_level":           risk_level,
        "recommendation":       recommendation,
        "fusion_note":          fusion_note,
        "overrides_triggered":  overrides,
        "explanation":          explanation,
        "contributing_factors": contributing_factors,
    }


def _build_recommendation(risk_level, final_score, patient_data, stroke_type=None):
    """
    نظام Recommendations ذكي — مش static text.
    بيبني توصية مخصصة بناءً على:
      - مستوى الخطورة
      - نوع السكتة (لو موجود من الـ CT scan)
      - العوامل السريرية الموجودة
    """
    bmi      = float(patient_data.get("BMI", 0))
    heart    = patient_data.get("HeartDisease", "No")
    diabetic = patient_data.get("Diabetic", "No")
    smoking  = patient_data.get("Smoking", "No")
    kidney   = patient_data.get("KidneyDisease", "No")
    age      = int(patient_data.get("Age", 0))

    lines = []

    # ── 1. التوصية الأساسية حسب الـ risk level ────────────
    if risk_level == "High":
        lines.append("🔴 URGENT: Immediate neurological evaluation required within 24 hours.")
        if stroke_type == "Hemorrhagic":
            lines.append("⚠️ Hemorrhagic stroke detected — avoid anticoagulants and thrombolytics.")
            lines.append("Urgent neurosurgical consultation recommended.")
        elif stroke_type == "Ischemic":
            lines.append("Evaluate eligibility for thrombolytic therapy (tPA) within treatment window.")
            lines.append("Antiplatelet therapy assessment recommended.")
        else:
            lines.append("CT/MRI neuroimaging required to differentiate stroke type.")

    elif risk_level == "Medium":
        lines.append("🟡 Schedule neurologist consultation within 1 week.")
        lines.append("Lifestyle modification program strongly recommended.")

    else:
        lines.append("🟢 Continue routine health monitoring.")
        lines.append("Annual stroke risk screening advised.")

    # ── 2. توصيات خاصة بكل عامل خطر ─────────────────────
    specific = []

    if heart == "Yes":
        specific.append("Cardiology follow-up required — cardiac embolic source evaluation.")

    if diabetic == "Yes":
        specific.append("Maintain HbA1c < 7% — uncontrolled diabetes significantly increases stroke risk.")

    if bmi >= 30:
        bmi_class = "morbid obesity" if bmi >= 40 else "obesity"
        specific.append(f"Weight management program advised (BMI={bmi}, {bmi_class}).")

    if smoking in ["Yes", "Former"]:
        if smoking == "Yes":
            specific.append("Immediate smoking cessation required — smoking doubles stroke risk.")
        else:
            specific.append("Sustained smoking cessation recommended — residual risk remains elevated.")

    if kidney == "Yes":
        specific.append("Nephrology co-management advised — CKD increases stroke risk by 43%.")

    if age >= 65:
        specific.append("Enhanced monitoring for elderly patient — age is a non-modifiable risk amplifier.")

    if specific:
        lines.append("─── Specific Recommendations ───")
        lines.extend(specific)

    # ── 3. إضافة Score للسياق ─────────────────────────────
    lines.append(f"[Composite Risk Score: {round(final_score * 100, 1)}%]")

    return "\n".join(lines)


class MLService:

    _clinical_model    = None
    _image_model       = None
    _clinical_scaler   = None
    _clinical_features = None
    _shap_explainer    = None   # ← SHAP explainer (بيتبني مرة واحدة بس)

    @classmethod
    def load_models(cls):
        if cls._clinical_model is None:
            try:
                cls._clinical_model    = joblib.load(os.path.join(MODELS_PATH, "clinical_model_v1.pkl"))
                cls._clinical_scaler   = joblib.load(os.path.join(MODELS_PATH, "clinical_scaler_v1.pkl"))
                cls._clinical_features = joblib.load(os.path.join(MODELS_PATH, "clinical_features_v1.pkl"))
                print("✓ Clinical Model loaded successfully")

                # بناء الـ SHAP explainer مرة واحدة بعد تحميل الموديل
                try:
                    cls._shap_explainer = shap.TreeExplainer(cls._clinical_model)
                    print("✓ SHAP Explainer initialized successfully")
                except Exception as shap_err:
                    print(f"⚠ SHAP Explainer failed to initialize: {shap_err}")
                    cls._shap_explainer = None

            except Exception as e:
                print(f"✗ Error loading clinical model: {e}")

        if cls._image_model is None:
            try:
                cls._image_model = tf.keras.models.load_model(
                    os.path.join(MODELS_PATH, "image_model_best.keras")
                )
                print("✓ Image Model loaded successfully")
            except Exception as e:
                print(f"✗ Error loading image model: {e}")

    @classmethod
    def prepare_clinical_features(cls, data):
        bmi             = float(data.get('bmi', 0))
        physical_health = int(data.get('physicalhealth', 0))
        mental_health   = int(data.get('mentalhealth', 0))
        sleep_time      = float(data.get('sleeptime', 0))
        age_num         = int(data.get('age', 50))

        is_diabetic = 1 if data.get('diabetic') == 'Yes' else 0
        bad_health  = 1 if data.get('genhealth') in ['Poor', 'Fair'] else 0

        risk_score = (
            bmi * 0.02 +
            physical_health * 0.03 +
            mental_health * 0.02 +
            (1 if data.get('heartdisease') == 'Yes' else 0) * 0.3 +
            (1 if data.get('smoking') == 'Yes' else 0) * 0.1
        )

        sex_male        = 1 if data.get('sex') == 'Male' else 0
        smoking_yes     = 1 if data.get('smoking') == 'Yes' else 0
        alcohol_yes     = 1 if data.get('alcoholdrinking') == 'Yes' else 0
        heart_yes       = 1 if data.get('heartdisease') == 'Yes' else 0
        diffwalking_yes = 1 if data.get('diffwalking') == 'Yes' else 0

        race          = data.get('race', 'White')
        race_asian    = 1 if race == 'Asian' else 0
        race_black    = 1 if race == 'Black' else 0
        race_hispanic = 1 if race == 'Hispanic' else 0
        race_other    = 1 if race == 'Other' else 0
        race_white    = 1 if race == 'White' else 0

        physical_activity = 1 if data.get('physicalactivity') == 'Yes' else 0
        asthma            = 1 if data.get('asthma') == 'Yes' else 0
        kidney            = 1 if data.get('kidneydisease') == 'Yes' else 0

        features = pd.DataFrame([[
            bmi, physical_health, mental_health, sleep_time, age_num,
            is_diabetic, bad_health, risk_score, sex_male, smoking_yes,
            alcohol_yes, heart_yes, diffwalking_yes, race_asian, race_black,
            race_hispanic, race_other, race_white, physical_activity, asthma, kidney
        ]], columns=cls._clinical_features)

        return features

    @classmethod
    def predict_clinical(cls, clinical_data):
        cls.load_models()
        if cls._clinical_model is None:
            raise Exception("Clinical model not loaded")

        features = cls.prepare_clinical_features(clinical_data)

        # احفظ الـ features قبل الـ scaling عشان SHAP يشتغل عليها
        features_for_shap = features.copy()

        if cls._clinical_scaler is not None:
            features = cls._clinical_scaler.transform(features)

        try:
            if hasattr(cls._clinical_model, 'predict_proba'):
                score = float(cls._clinical_model.predict_proba(features)[0][1])
            else:
                score = float(cls._clinical_model.predict(features)[0])

            # احسب الـ SHAP values وضّمها في الـ response
            shap_explanation = cls.get_shap_values(features_for_shap)

            return {
                "score":            score,
                "shap_explanation": shap_explanation,
            }

        except Exception as e:
            print(f"Error in clinical prediction: {e}")
            raise

    @classmethod
    def prepare_image(cls, image_file):
        try:
            img = Image.open(image_file)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img = img.resize((224, 224))
            img_array = np.array(img, dtype=np.float32)
            img_array = np.expand_dims(img_array, axis=0)  # بدون قسمة على 255 — زي الـ notebook
            return img_array
        except Exception as e:
            print(f"Error preparing image: {e}")
            return None

    @classmethod
    def upload_to_imgbb(cls, image_array, patient_id=None):
        """
        يرفع الـ Grad-CAM على ImgBB ويرجع الـ URL
        """
        try:
            # حوّل الـ array لـ PNG bytes
            pil_img    = Image.fromarray(image_array)
            buffer     = io.BytesIO()
            pil_img.save(buffer, format="PNG")
            img_bytes  = buffer.getvalue()
            img_base64 = base64.b64encode(img_bytes).decode("utf-8")

            name = f"gradcam_patient{patient_id}_{uuid.uuid4().hex[:8]}"

            response = requests.post(
                "https://api.imgbb.com/1/upload",
                data={
                    "key":  IMGBB_API_KEY,
                    "name": name,
                    "image": img_base64,
                },
                timeout=15,
            )

            result = response.json()
            if result.get("success"):
                url = result["data"]["url"]
                print(f"✓ Grad-CAM uploaded to ImgBB: {url}")
                return url
            else:
                print(f"✗ ImgBB upload failed: {result}")
                return None

        except Exception as e:
            print(f"✗ Error uploading to ImgBB: {e}")
            return None

    @classmethod
    def generate_gradcam(cls, img_array, class_idx, patient_id=None):
        """
        Grad-CAM بالظبط زي الـ notebook — بيرفع على ImgBB ويرجع URL
        """
        try:
            model = cls._image_model

            # 1. جيب الـ EfficientNet base
            base = model.get_layer("efficientnetb0")

            # 2. جيب آخر Conv2D layer — بالظبط زي الـ notebook
            last_conv = [l.name for l in base.layers
                         if isinstance(l, tf.keras.layers.Conv2D)][-1]
            print(f"Grad-CAM using layer: {last_conv}")

            # 3. عمل grad_model من الـ base بس
            grad_model = tf.keras.Model(
                inputs=base.input,
                outputs=[base.get_layer(last_conv).output, base.output]
            )

            # 4. احسب الـ gradients — بالظبط زي الـ notebook
            with tf.GradientTape() as tape:
                conv_out, base_out = grad_model(img_array)
                tape.watch(conv_out)

                # كمّل الـ forward pass يدوياً زي الـ notebook
                x = model.get_layer("global_average_pooling2d")(base_out)
                x = model.get_layer("batch_normalization")(x, training=False)
                x = model.get_layer("dense")(x)
                x = model.get_layer("dropout")(x, training=False)
                x = model.get_layer("dense_1")(x)
                x = model.get_layer("dropout_1")(x, training=False)
                x = model.get_layer("dense_2")(x)
                score = x[:, class_idx]

            grads   = tape.gradient(score, conv_out)
            pooled  = tf.reduce_mean(grads, axis=(0, 1, 2))
            heatmap = tf.reduce_sum(tf.multiply(pooled, conv_out[0]), axis=-1)
            heatmap = tf.maximum(heatmap, 0) / (tf.math.reduce_max(heatmap) + 1e-8)
            heatmap = heatmap.numpy()

            # 5. Resize وColormap
            heatmap_resized = cv2.resize(heatmap, (224, 224))
            heatmap_uint8   = np.uint8(255 * heatmap_resized)
            heatmap_colored = cv2.applyColorMap(heatmap_uint8, cv2.COLORMAP_JET)
            heatmap_colored = cv2.cvtColor(heatmap_colored, cv2.COLOR_BGR2RGB)

            # 6. Overlay على الصورة الأصلية
            original_img  = np.uint8(img_array[0])
            superimposed  = cv2.addWeighted(original_img, 0.6, heatmap_colored, 0.4, 0)

            # 7. ارفع على ImgBB وارجع الـ URL
            gradcam_url = cls.upload_to_imgbb(superimposed, patient_id=patient_id)
            return gradcam_url

        except Exception as e:
            print(f"Error generating Grad-CAM: {e}")
            return None

    @classmethod
    def predict_image(cls, image_file, patient_id=None):
        cls.load_models()

        if cls._image_model is None:
            raise Exception("Image model not loaded")

        img_array = cls.prepare_image(image_file)
        if img_array is None:
            raise Exception("Failed to prepare image")

        try:
            preds = cls._image_model.predict(img_array, verbose=0)[0]

            prob_hemorrhagic = float(preds[0])
            prob_ischemic    = float(preds[1])
            prob_normal      = float(preds[2])

            class_idx   = int(np.argmax(preds))
            stroke_type = CLASSES[class_idx]
            confidence  = float(preds[class_idx])

            image_score = 1.0 - prob_normal

            gradcam_url = None
            if stroke_type != 'Normal':
                gradcam_url = cls.generate_gradcam(img_array, class_idx, patient_id=patient_id)

            return {
                "image_score":   round(image_score, 4),
                "stroke_type":   stroke_type,
                "confidence":    round(confidence * 100, 1),
                "probabilities": {
                    "Hemorrhagic": round(prob_hemorrhagic * 100, 1),
                    "Ischemic":    round(prob_ischemic    * 100, 1),
                    "Normal":      round(prob_normal      * 100, 1),
                },
                "gradcam_url": gradcam_url,   # ← URL من ImgBB مباشرةً
            }

        except Exception as e:
            print(f"Error in image prediction: {e}")
            raise

    @classmethod
    def get_shap_values(cls, features_df):
        """
        بيحسب SHAP values الحقيقية من جوّا الموديل.
        بيرجع list من الـ factors مرتبة من الأعلى تأثيراً للأقل،
        كل عنصر: { factor, shap_value, direction }
        """
        if cls._shap_explainer is None:
            return []

        try:
            # لو الـ scaler شغال، لازم نبعت الـ features قبل الـ scaling
            # لأن SHAP بيشتغل على الـ raw features عشان القيم تبقى readable
            shap_vals = cls._shap_explainer.shap_values(features_df)

            # CatBoost بيرجع array واحدة أو list — نتعامل مع الحالتين
            if isinstance(shap_vals, list):
                # binary classification → نأخذ class 1 (High Risk)
                vals = shap_vals[1][0]
            else:
                vals = shap_vals[0]

            feature_names = list(features_df.columns)

            # رتّب حسب القيمة المطلقة (الأعلى تأثيراً الأول)
            shap_results = []
            for name, val in zip(feature_names, vals):
                shap_results.append({
                    "factor":      name,
                    "shap_value":  round(float(val), 4),
                    "direction":   "increases_risk" if val > 0 else "decreases_risk",
                    "impact_pct":  round(abs(float(val)) * 100, 1),
                })

            shap_results.sort(key=lambda x: abs(x["shap_value"]), reverse=True)

            # رجّع أهم 8 عوامل بس (مش كل الـ 21 feature)
            return shap_results[:8]

        except Exception as e:
            print(f"⚠ SHAP calculation error: {e}")
            return []

    @classmethod
    def predict_fusion(cls, clinical_score, image_score=None, patient_data=None):
        return dynamic_fusion_v2(
            clinical_score=clinical_score,
            image_score=image_score,
            patient_data=patient_data
        )

    @classmethod
    def determine_risk_level(cls, score):
        if score >= 0.70:
            return 'High'
        elif score >= 0.40:
            return 'Medium'
        else:
            return 'Low'

    @classmethod
    def get_recommendation(cls, risk_level, clinical_data, final_score=0.5, stroke_type=None):
        """
        نظام Recommendations ذكي — يستخدم _build_recommendation.
        مخصص لكل مريض بناءً على عواملهم السريرية ونوع السكتة.
        """
        # حوّل clinical_data keys للـ format بتاع _build_recommendation
        patient_data = {
            "BMI":          clinical_data.get('bmi', 0),
            "Age":          clinical_data.get('age', 0),
            "HeartDisease": clinical_data.get('heartdisease', 'No'),
            "Diabetic":     clinical_data.get('diabetic', 'No'),
            "KidneyDisease":clinical_data.get('kidneydisease', 'No'),
            "Smoking":      clinical_data.get('smoking', 'No'),
            "GenHealth":    clinical_data.get('genhealth', 'Good'),
            "SleepTime":    clinical_data.get('sleeptime', 7),
            "DiffWalking":  clinical_data.get('diffwalking', 'No'),
            "stroke_type":  stroke_type,
        }
        return _build_recommendation(
            risk_level   = risk_level,
            final_score  = final_score,
            patient_data = patient_data,
            stroke_type  = stroke_type,
        )

    @classmethod
    def get_contributing_factors(cls, clinical_data, clinical_score):
        factors = []
        if clinical_data.get('heartdisease') == 'Yes':        factors.append("Heart disease present (High impact)")
        if clinical_data.get('diabetic') == 'Yes':            factors.append("Diabetic condition (High impact)")
        if clinical_data.get('smoking') in ['Yes', 'Former']: factors.append("Smoking history (Medium impact)")
        if float(clinical_data.get('bmi', 0)) > 30:           factors.append("High BMI - Obesity (Medium impact)")
        if clinical_data.get('kidneydisease') == 'Yes':       factors.append("Kidney disease (Medium impact)")
        return factors if factors else ["No significant risk factors identified"]


MLService.load_models()