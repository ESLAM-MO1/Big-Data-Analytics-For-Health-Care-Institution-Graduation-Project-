from django.db import models, connection
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
    overrides_triggered = models.TextField(blank=True, null=True)
    explanation = models.TextField(blank=True, null=True)
    contributing_factors = models.TextField(blank=True, null=True)

    # Metadata
    model_version = models.CharField(max_length=50, default='v1.0')
    created_at = models.DateTimeField(auto_now_add=True)
    prediction_type = models.CharField(max_length=50, default='fusion')

    class Meta:
        db_table = 'predictions'
        ordering = ['-created_at']

    def __str__(self):
        return f"Prediction for {self.patient.full_name} - {self.risk_level}"

    def set_contributing_factors(self, factors_list):
        import json
        self.contributing_factors = json.dumps(factors_list)

    def get_contributing_factors(self):
        import json
        if self.contributing_factors:
            try:
                return json.loads(self.contributing_factors)
            except:
                return []
        return []

    def set_overrides_triggered(self, overrides_list):
        import json
        self.overrides_triggered = json.dumps(overrides_list)

    def get_overrides_triggered(self):
        import json
        if self.overrides_triggered:
            try:
                return json.loads(self.overrides_triggered)
            except:
                return []
        return []


# ══════════════════════════════════════════
# Prescription Model  ← الجديد
# ══════════════════════════════════════════

class Prescription(models.Model):
    """روشتات المرضى"""
    id           = models.AutoField(primary_key=True)
    patient      = models.ForeignKey(Patients, on_delete=models.CASCADE, related_name='prescriptions')
    doc          = models.ForeignKey(User, on_delete=models.CASCADE, related_name='prescriptions')
    prescription = models.TextField()
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'prescriptions'
        ordering = ['-created_at']

    def __str__(self):
        return f"Prescription for {self.patient.full_name} by Dr.{self.doc.username}"


# ══════════════════════════════════════════════════════════
# Database Views  (managed = False → Django مش هيعملهم migrate)
# ══════════════════════════════════════════════════════════

class AllPatientsView(models.Model):
    patient_id        = models.IntegerField(primary_key=True)
    full_name         = models.CharField(max_length=200)
    age               = models.IntegerField()
    sex               = models.CharField(max_length=10)
    predictions_count = models.IntegerField()
    last_risk         = models.CharField(max_length=20, null=True, blank=True)
    registered_at     = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed  = False
        db_table = 'all_patients_view'

    def __str__(self):
        return f"{self.full_name} - {self.age}y"


class AllPredictionsView(models.Model):
    full_name            = models.CharField(max_length=200, primary_key=True)
    age                  = models.IntegerField()
    sex                  = models.CharField(max_length=10)
    final_score          = models.FloatField(null=True, blank=True)
    contributing_factors = models.TextField(null=True, blank=True)
    clinical_score       = models.FloatField(null=True, blank=True)
    image_score          = models.FloatField(null=True, blank=True)

    class Meta:
        managed  = False
        db_table = 'all_predictions_view'

    def __str__(self):
        return f"{self.full_name}"


class PatientsCountView(models.Model):
    total_patients = models.IntegerField(primary_key=True)

    class Meta:
        managed  = False
        db_table = 'patients_count_view'


class PredictionsCountView(models.Model):
    total_predictions = models.IntegerField(primary_key=True)

    class Meta:
        managed  = False
        db_table = 'predictions_count_view'


# ══════════════════════════════════════════════════════════
# DB Function Helper: search_patient_by_name
# ══════════════════════════════════════════════════════════

def search_patient_by_name(name: str) -> list:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM search_patient_by_name(%s)",
            [name]
        )
        columns = [col[0] for col in cursor.description]
        rows    = cursor.fetchall()

    return [dict(zip(columns, row)) for row in rows]

# ══════════════════════════════════════════════════════════
# NEW: Self-Evolving System — ConfirmedCase
# الحالات المؤكدة من الدكتور، بتتراكم وبتشغل الـ retrain
# ══════════════════════════════════════════════════════════

class ConfirmedCase(models.Model):
    """
    كل حالة يأكدها الدكتور بتتحفظ هنا.
    لما يتجمع RETRAIN_THRESHOLD حالة → الموديل بيعمل retrain تلقائي.
    """

    # ربط بالمريض والتنبؤ الأصلي
    patient    = models.ForeignKey(Patients,    on_delete=models.CASCADE, related_name='confirmed_cases')
    prediction = models.ForeignKey(Predictions, on_delete=models.SET_NULL, null=True, blank=True, related_name='confirmed_cases')

    # البيانات السريرية (نسخة من ClinicalData وقت التأكيد)
    age             = models.IntegerField()
    sex             = models.CharField(max_length=10)
    bmi             = models.FloatField()
    smoking         = models.CharField(max_length=50)
    heartdisease    = models.CharField(max_length=10)
    diabetic        = models.CharField(max_length=10)
    kidneydisease   = models.CharField(max_length=10)
    diffwalking     = models.CharField(max_length=10)
    genhealth       = models.CharField(max_length=50)
    sleeptime       = models.FloatField()
    physicalhealth  = models.IntegerField()
    mentalhealth    = models.IntegerField()

    # نتيجة النظام وقت التنبؤ
    system_prediction  = models.CharField(max_length=20)   # High / Medium / Low
    system_confidence  = models.FloatField()               # 0.0 → 1.0

    # تأكيد الدكتور
    doctor_confirmed_label = models.CharField(max_length=20)  # High / Medium / Low
    confirmed_by           = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='confirmed_cases')
    confirmed_at           = models.DateTimeField(auto_now_add=True)

    # حالة الاستخدام في التدريب
    used_in_training    = models.BooleanField(default=False)
    training_version    = models.CharField(max_length=20, blank=True, null=True)  # الـ version اللي اتدرب عليها

    class Meta:
        db_table = 'confirmed_cases'
        ordering = ['-confirmed_at']

    def __str__(self):
        return f"ConfirmedCase #{self.pk} — {self.patient.full_name} ({self.doctor_confirmed_label})"


# ══════════════════════════════════════════════════════════
# NEW: Self-Evolving System — ModelVersion
# سجل كل إصدارات الموديل (مش بنلغي القديم أبداً)
# ══════════════════════════════════════════════════════════

class ModelVersion(models.Model):
    """
    كل version بتتحفظ هنا مع accuracy ومتى اتدربت.
    الـ active version هي اللي is_active=True.
    في أي وقت ممكن نعمل rollback لأي version قديمة.
    """

    STATUS_CHOICES = [
        ('active',   'Active'),
        ('archived', 'Archived'),
        ('failed',   'Failed'),
    ]

    version_name   = models.CharField(max_length=20, unique=True)   # v1, v2, v3 ...
    file_path      = models.CharField(max_length=500)               # المسار الكامل للـ .cbm
    accuracy       = models.FloatField()                            # دقة على الـ test set
    cases_count    = models.IntegerField(default=0)                 # عدد الحالات اللي اتدرب عليها
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='archived')
    is_active      = models.BooleanField(default=False)             # الـ active version بس
    trained_at     = models.DateTimeField(auto_now_add=True)
    notes          = models.TextField(blank=True, null=True)        # ملاحظات اختيارية

    class Meta:
        db_table = 'model_versions'
        ordering = ['-trained_at']

    def __str__(self):
        return f"ModelVersion {self.version_name} — acc={self.accuracy:.3f} ({'ACTIVE' if self.is_active else 'archived'})"