from django.db import models
from django.contrib.auth.models import User

class Patients(models.Model):
    """نموذج المرضى"""
    id = models.AutoField(primary_key=True)
    full_name = models.CharField(max_length=200)
    age = models.IntegerField()
    sex = models.CharField(max_length=10, choices=[('Male', 'Male'), ('Female', 'Female')])
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'patients'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.full_name} - {self.age}y"


class ClinicalData(models.Model):
    """البيانات السريرية للمريض"""
    id = models.AutoField(primary_key=True)
    patient = models.ForeignKey(Patients, on_delete=models.CASCADE, related_name='clinical_records')
    
    # Clinical Features
    bmi = models.FloatField()
    smoking = models.CharField(max_length=50)
    heartdisease = models.CharField(max_length=10)
    diabetic = models.CharField(max_length=10)
    kidneydisease = models.CharField(max_length=10)
    diffwalking = models.CharField(max_length=10)
    genhealth = models.CharField(max_length=50)
    sleeptime = models.FloatField()
    physicalhealth = models.IntegerField()
    mentalhealth = models.IntegerField()
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    prediction_type = models.CharField(max_length=50, default='clinical')
    
    class Meta:
        db_table = 'clinical_data'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Clinical Data for {self.patient.full_name}"


class CtImages(models.Model):
    """صور الأشعة المقطعية"""
    id = models.AutoField(primary_key=True)
    patient = models.ForeignKey(Patients, on_delete=models.CASCADE, related_name='ct_scans')
    
    # Image paths
    image_path = models.CharField(max_length=500)
    gradcam_path = models.CharField(max_length=500, blank=True, null=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    prediction_type = models.CharField(max_length=50, default='image')
    
    class Meta:
        db_table = 'ct_images'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"CT Scan for {self.patient.full_name}"


class Predictions(models.Model):
    """نتائج التنبؤات"""
    id = models.AutoField(primary_key=True)
    patient = models.ForeignKey(Patients, on_delete=models.CASCADE, related_name='predictions')
    
    # Scores
    clinical_score = models.FloatField(null=True, blank=True)
    image_score = models.FloatField(null=True, blank=True)
    final_score = models.FloatField()
    
    # Risk Assessment
    risk_level = models.CharField(max_length=20)  # Low, Medium, High
    recommendation = models.TextField()
    
    # Additional Info
    fusion_note = models.TextField(blank=True, null=True)
    
    # ✅ الإصلاح: استخدام TextField بدلاً من JSONField
    overrides_triggered = models.TextField(blank=True, null=True)  # سيتم تخزين JSON كـ string
    explanation = models.TextField(blank=True, null=True)
    contributing_factors = models.TextField(blank=True, null=True)  # سيتم تخزين JSON كـ string
    
    # Metadata
    model_version = models.CharField(max_length=50, default='v1.0')
    created_at = models.DateTimeField(auto_now_add=True)
    prediction_type = models.CharField(max_length=50, default='fusion')
    
    class Meta:
        db_table = 'predictions'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Prediction for {self.patient.full_name} - {self.risk_level}"
    
    # ✅ Helper methods للتعامل مع JSON
    def set_contributing_factors(self, factors_list):
        """تحويل list إلى JSON string"""
        import json
        self.contributing_factors = json.dumps(factors_list)
    
    def get_contributing_factors(self):
        """تحويل JSON string إلى list"""
        import json
        if self.contributing_factors:
            try:
                return json.loads(self.contributing_factors)
            except:
                return []
        return []
    
    def set_overrides_triggered(self, overrides_list):
        """تحويل list إلى JSON string"""
        import json
        self.overrides_triggered = json.dumps(overrides_list)
    
    def get_overrides_triggered(self):
        """تحويل JSON string إلى list"""
        import json
        if self.overrides_triggered:
            try:
                return json.loads(self.overrides_triggered)
            except:
                return []
        return []