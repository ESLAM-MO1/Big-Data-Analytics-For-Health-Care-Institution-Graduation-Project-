def dynamic_fusion_v2(clinical_score, image_score=None, patient_data=None):
    """
    Enhanced Dynamic Late Fusion
    Override Rules + Explainability
    Based on Stroke Prediction Dataset
    """
    contributing_factors = []
    overrides = []

    # ─── STEP 1: Dynamic Late Fusion ───
    if image_score is None:
        fused_score = clinical_score
        fusion_note = "Clinical model only (no imaging available)"
    else:
        w_img  = image_score
        w_clin = 1 - image_score
        fused_score = (w_img * image_score) + (w_clin * clinical_score)
        fusion_note = f"Fused: image={w_img:.0%}, clinical={w_clin:.0%}"

    final_score = fused_score

    # ─── STEP 2: Override Rules ───
    if patient_data:
        bmi          = float(patient_data.get("BMI", 0))
        age_cat      = patient_data.get("AgeCategory", "")
        heart        = patient_data.get("HeartDisease", "No")
        diabetic     = patient_data.get("Diabetic", "No")
        kidney       = patient_data.get("KidneyDisease", "No")
        smoking      = patient_data.get("Smoking", "No")
        gen_health   = patient_data.get("GenHealth", "Good")
        sleep_time   = float(patient_data.get("SleepTime", 7))
        diff_walking = patient_data.get("DiffWalking", "No")
        elderly_cats = ["75-79", "80 or older"]

        if bmi >= 40:
            final_score = max(final_score, 0.80)
            overrides.append("BMI >= 40 (morbid obesity) → floored to 0.80")

        if heart == "Yes":
            final_score = max(final_score, 0.75)
            overrides.append("Heart disease history → floored to 0.75")

        if age_cat in elderly_cats and diabetic == "Yes":
            final_score = max(final_score, 0.78)
            overrides.append("Age 75+ with diabetes → floored to 0.78")

        if kidney == "Yes":
            final_score = min(final_score + 0.10, 1.0)
            overrides.append("Kidney disease → score boosted +0.10")

        risk_count = sum([
            heart == "Yes", diabetic == "Yes", smoking == "Yes",
            kidney == "Yes", bmi >= 30, age_cat in elderly_cats,
        ])
        if risk_count >= 4:
            final_score = max(final_score, 0.85)
            overrides.append(f"{risk_count} compounding factors → floored to 0.85")

        # ─── STEP 3: Explainability ───
        fw = {}
        if image_score is not None:
            fw["Imaging Result"] = round(w_img * image_score, 3)
            fw["Clinical Model"] = round(w_clin * clinical_score, 3)
        else:
            fw["Clinical Model"] = round(clinical_score, 3)

        if heart == "Yes":                     fw["Heart Disease"]       = 0.15
        if diabetic == "Yes":                  fw["Diabetes"]            = 0.10
        if bmi >= 30:                          fw["High BMI"]            = round((bmi - 18.5) / 100, 3)
        if smoking == "Yes":                   fw["Smoking"]             = 0.08
        if kidney == "Yes":                    fw["Kidney Disease"]      = 0.10
        if diff_walking == "Yes":              fw["Difficulty Walking"]  = 0.06
        if gen_health in ["Fair", "Poor"]:     fw["Poor General Health"] = 0.07
        if sleep_time < 6 or sleep_time > 9:   fw["Abnormal Sleep"]      = 0.04

        total = sum(fw.values())
        contributing_factors = [
            {"factor": k, "weight": round(v / total * 100, 1)}
            for k, v in sorted(fw.items(), key=lambda x: -x[1])
        ]

        top3 = [f["factor"] for f in contributing_factors[:3]]
        explanation = f"Risk driven by: {', '.join(top3)}."
        if overrides:
            explanation += " Medical override rules triggered."
    else:
        explanation = fusion_note

    # ─── STEP 4: Risk Stratification ───
    if final_score < 0.40:
        risk_level     = "LOW"
        recommendation = "Annual monitoring recommended."
    elif final_score < 0.70:
        risk_level     = "MEDIUM"
        recommendation = "Follow-up within 3 months advised."
    else:
        risk_level     = "HIGH"
        recommendation = "Immediate neurological evaluation required."

    return {
        "final_score":          round(float(final_score), 4),
        "risk_level":           risk_level,
        "recommendation":       recommendation,
        "fusion_note":          fusion_note,
        "overrides_triggered":  overrides,
        "explanation":          explanation,
        "contributing_factors": contributing_factors,
    }



# EXAMPLE

if __name__ == "__main__":
    patient = {
        "BMI": 34.5, "Smoking": "Yes", "AlcoholDrinking": "No",
        "HeartDisease": "Yes", "PhysicalHealth": 20, "MentalHealth": 10,
        "DiffWalking": "No", "Diabetic": "Yes", "AgeCategory": "75-79",
        "GenHealth": "Fair", "SleepTime": 5, "KidneyDisease": "Yes",
    }

    result = dynamic_fusion_v2(
        clinical_score=0.62,
        image_score=0.55,
        patient_data=patient
    )

    print("=" * 55)
    print(f"Final Score   : {result['final_score']}")
    print(f"Risk Level    : {result['risk_level']}")
    print(f"Recommendation: {result['recommendation']}")
    print(f"\nFusion Note   : {result['fusion_note']}")
    print(f"\nExplanation   : {result['explanation']}")

    if result['overrides_triggered']:
        print("\nOverrides Triggered:")
        for o in result['overrides_triggered']:
            print(f"  ⚠  {o}")

    print("\nContributing Factors:")
    for f in result['contributing_factors']:
        bar = '█' * int(f['weight'] / 4)
        print(f"  {f['factor']:<28} {bar} {f['weight']}%")
    print("=" * 55)