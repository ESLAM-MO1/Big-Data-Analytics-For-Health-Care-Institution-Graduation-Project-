from rest_framework import serializers
from .models import Patients, ClinicalData, CtImages, Predictions


class PatientSerializer(serializers.ModelSerializer):
  
    class Meta:
        model = Patients
        fields = '__all__'
        read_only_fields = ['id', 'created_at']


class ClinicalDataSerializer(serializers.ModelSerializer):
    """تحويل Clinical Data لـ JSON"""
    patient_name = serializers.CharField(source='patient.full_name', read_only=True)
    
    class Meta:
        model = ClinicalData
        fields = '__all__'
        read_only_fields = ['id', 'created_at']


class CtImageSerializer(serializers.ModelSerializer):
   
    patient_name = serializers.CharField(source='patient.full_name', read_only=True)
    
    class Meta:
        model = CtImages
        fields = '__all__'
        read_only_fields = ['id', 'created_at']


class PredictionSerializer(serializers.ModelSerializer):
    """تحويل Predictions لـ JSON"""
    patient_name = serializers.CharField(source='patient.full_name', read_only=True)
    patient_age = serializers.IntegerField(source='patient.age', read_only=True)
    patient_sex = serializers.CharField(source='patient.sex', read_only=True)
    
    class Meta:
        model = Predictions
        fields = '__all__'
        read_only_fields = ['id', 'created_at']


class PredictionInputSerializer(serializers.Serializer):
    
    # Patient Basic Info
    patient_id = serializers.IntegerField(required=False)
    full_name = serializers.CharField(max_length=200, required=False)
    age = serializers.IntegerField(required=False)
    sex = serializers.ChoiceField(choices=['Male', 'Female'], required=False)
    
    # Clinical Data
    bmi = serializers.FloatField()
    smoking = serializers.CharField(max_length=50)
    heartdisease = serializers.CharField(max_length=10)
    diabetic = serializers.CharField(max_length=10)
    kidneydisease = serializers.CharField(max_length=10)
    diffwalking = serializers.CharField(max_length=10)
    genhealth = serializers.CharField(max_length=50)
    sleeptime = serializers.FloatField()
    physicalhealth = serializers.IntegerField()
    mentalhealth = serializers.IntegerField()
    
    # Image (optional)
    ct_scan = serializers.ImageField(required=False)


class PredictionResponseSerializer(serializers.Serializer):
   
    success = serializers.BooleanField()
    patient_id = serializers.IntegerField()
    prediction_id = serializers.IntegerField()
    
    # Scores
    clinical_score = serializers.FloatField()
    image_score = serializers.FloatField()
    final_score = serializers.FloatField()
    
    # Risk Assessment
    risk_level = serializers.CharField()
    recommendation = serializers.CharField()
    contributing_factors = serializers.ListField()
    
    # Message
    message = serializers.CharField()
