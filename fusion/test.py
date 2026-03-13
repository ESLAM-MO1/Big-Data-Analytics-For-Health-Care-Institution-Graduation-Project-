from fusion_engine import dynamic_fusion_v2


patient = {
    "BMI": 34.5,
    "Smoking": "Yes",
    "HeartDisease": "Yes",
    "Diabetic": "Yes",
    "AgeCategory": "75-79",
    "GenHealth": "Fair",
    "SleepTime": 5,
    "KidneyDisease": "Yes",
    "DiffWalking": "No"
}

result = dynamic_fusion_v2(
    clinical_score=0.62,
    image_score=0.55,
    patient_data=patient
)

print(result)