#python manage.py runserver
from rest_framework.decorators import api_view, parser_classes, permission_classes, authentication_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import json
import os
import numpy as np
from PIL import Image

from .models import (
    Patients, ClinicalData, CtImages, Predictions, Prescription,
    AllPatientsView, AllPredictionsView,
    PatientsCountView, PredictionsCountView,
    search_patient_by_name,
)
from .serializers import (
    PatientSerializer,
    ClinicalDataSerializer,
    CtImageSerializer,
    PredictionSerializer,
    PrescriptionSerializer,
    PredictionInputSerializer,
    PredictionResponseSerializer
)
from .ml_service import MLService


# ══════════════════════════════════════════
# Authentication APIs
# ══════════════════════════════════════════

@api_view(['POST'])
@permission_classes([AllowAny])
def register_view(request):
    """تسجيل مستخدم جديد وإرجاع Token"""
    username = request.data.get('username', '').strip()
    password = request.data.get('password', '').strip()
    email    = request.data.get('email', '').strip()

    if not username or not password:
        return Response({'success': False, 'message': 'اسم المستخدم وكلمة المرور مطلوبان'}, status=status.HTTP_400_BAD_REQUEST)

    if len(password) < 8:
        return Response({'success': False, 'message': 'كلمة المرور لازم تكون 8 حروف على الأقل'}, status=status.HTTP_400_BAD_REQUEST)

    if User.objects.filter(username=username).exists():
        return Response({'success': False, 'message': 'اسم المستخدم ده موجود بالفعل'}, status=status.HTTP_400_BAD_REQUEST)

    if email and User.objects.filter(email=email).exists():
        return Response({'success': False, 'message': 'الإيميل ده مسجل بالفعل'}, status=status.HTTP_400_BAD_REQUEST)

    user = User.objects.create_user(username=username, password=password, email=email)
    token, _ = Token.objects.get_or_create(user=user)

    return Response({
        'success': True,
        'message': 'تم إنشاء الحساب بنجاح',
        'token': token.key,
        'user': {'id': user.id, 'username': user.username, 'email': user.email, 'is_staff': user.is_staff}
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    """تسجيل الدخول وإرجاع Token"""
    username = request.data.get('username', '').strip()
    password = request.data.get('password', '').strip()

    if not username or not password:
        return Response({'success': False, 'message': 'اسم المستخدم وكلمة المرور مطلوبان'}, status=status.HTTP_400_BAD_REQUEST)

    user = authenticate(username=username, password=password)

    if user is None:
        return Response({'success': False, 'message': 'اسم المستخدم أو كلمة المرور غلط'}, status=status.HTTP_401_UNAUTHORIZED)

    if not user.is_active:
        return Response({'success': False, 'message': 'الحساب موقوف'}, status=status.HTTP_403_FORBIDDEN)

    token, _ = Token.objects.get_or_create(user=user)

    return Response({
        'success': True,
        'message': 'تم تسجيل الدخول بنجاح',
        'token': token.key,
        'user': {'id': user.id, 'username': user.username, 'email': user.email, 'is_staff': user.is_staff}
    })


@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """تسجيل الخروج وحذف الـ Token"""
    try:
        request.user.auth_token.delete()
    except Exception:
        pass
    return Response({'success': True, 'message': 'تم تسجيل الخروج'})


# ══════════════════════════════════════════
# Patient Management APIs
# ══════════════════════════════════════════

@api_view(['GET', 'POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def patients_list(request):
    if request.method == 'GET':
        patients = Patients.objects.all()
        serializer = PatientSerializer(patients, many=True)
        return Response({'success': True, 'count': len(serializer.data), 'data': serializer.data})

    elif request.method == 'POST':
        serializer = PatientSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({'success': True, 'message': 'Patient created successfully', 'data': serializer.data}, status=status.HTTP_201_CREATED)
        return Response({'success': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def patient_detail(request, pk):
    try:
        patient = Patients.objects.get(pk=pk)
    except Patients.DoesNotExist:
        return Response({'success': False, 'message': 'Patient not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer    = PatientSerializer(patient)
        clinical_data = ClinicalData.objects.filter(patient=patient)
        ct_scans      = CtImages.objects.filter(patient=patient)
        predictions   = Predictions.objects.filter(patient=patient)
        prescriptions = Prescription.objects.filter(patient=patient)  # ← جديد

        return Response({
            'success':          True,
            'patient':          serializer.data,
            'clinical_records': ClinicalDataSerializer(clinical_data, many=True).data,
            'ct_scans':         CtImageSerializer(ct_scans, many=True).data,
            'predictions':      PredictionSerializer(predictions, many=True).data,
            'prescriptions':    PrescriptionSerializer(prescriptions, many=True).data,  # ← جديد
        })

    elif request.method == 'PUT':
        serializer = PatientSerializer(patient, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'success': True, 'message': 'Patient updated successfully', 'data': serializer.data})
        return Response({'success': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        patient.delete()
        return Response({'success': True, 'message': 'Patient deleted successfully'}, status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def search_patients(request):
    query = request.GET.get('q', '')
    if not query:
        return Response({'success': False, 'message': 'Search query is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        results = search_patient_by_name(query)
        return Response({'success': True, 'count': len(results), 'data': results, 'source': 'db_function'})
    except Exception as e:
        patients   = Patients.objects.filter(full_name__icontains=query)
        serializer = PatientSerializer(patients, many=True)
        return Response({'success': True, 'count': len(serializer.data), 'data': serializer.data, 'source': 'orm_fallback'})


# ══════════════════════════════════════════
# Predictions APIs
# ══════════════════════════════════════════

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def make_prediction(request):
    try:
        data = request.data

        # 1. Get or Create Patient
        if data.get('patient_id'):
            try:
                patient = Patients.objects.get(pk=data['patient_id'])
            except Patients.DoesNotExist:
                return Response({'success': False, 'message': 'Patient not found'}, status=status.HTTP_404_NOT_FOUND)
        else:
            patient = Patients.objects.create(
                full_name=data.get('full_name', 'Unknown'),
                age=data.get('age', 0),
                sex=data.get('sex', 'Male')
            )

        # 2. Save Clinical Data
        clinical_record = ClinicalData.objects.create(
            patient=patient,
            bmi=data['bmi'],
            smoking=data['smoking'],
            heartdisease=data['heartdisease'],
            diabetic=data['diabetic'],
            kidneydisease=data['kidneydisease'],
            diffwalking=data['diffwalking'],
            genhealth=data['genhealth'],
            sleeptime=data['sleeptime'],
            physicalhealth=data['physicalhealth'],
            mentalhealth=data['mentalhealth']
        )

        # 3. Run Clinical Model
        clinical_score = MLService.predict_clinical(data)

        # 4. Run Image Model (if image provided)
        image_score     = None
        image_result    = None
        ct_image_record = None

        ct_scan = request.FILES.get('ct_scan')
        if ct_scan:
            # ارفع الصورة الأصلية على ImgBB
            ct_scan.seek(0)
            original_img_array = np.array(
                Image.open(ct_scan).convert('RGB').resize((224, 224)),
                dtype=np.uint8
            )
            original_url = MLService.upload_to_imgbb(original_img_array, patient_id=patient.id)

            # شغّل المودل
            ct_scan.seek(0)
            image_result = MLService.predict_image(ct_scan, patient_id=patient.id)
            image_score  = image_result["image_score"]

            # احفظ في الـ DB — الاتنين URLs من ImgBB
            ct_image_record = CtImages.objects.create(
                patient=patient,
                image_path=original_url or "",
                gradcam_path=image_result.get('gradcam_url')
            )

        # 5. Run Fusion
        patient_context = {
            "BMI":           float(data.get("bmi", 0)),
            "HeartDisease":  data.get("heartdisease", "No"),
            "Diabetic":      data.get("diabetic", "No"),
            "KidneyDisease": data.get("kidneydisease", "No"),
            "Smoking":       data.get("smoking", "No"),
            "AgeCategory":   str(data.get("age", "")),
            "GenHealth":     data.get("genhealth", "Good"),
            "SleepTime":     float(data.get("sleeptime", 7)),
            "DiffWalking":   data.get("diffwalking", "No"),
        }
        fusion = MLService.predict_fusion(clinical_score, image_score, patient_context)

        final_score          = fusion["final_score"]
        risk_level           = fusion["risk_level"]
        recommendation       = fusion["recommendation"]
        contributing_factors = fusion["contributing_factors"]
        fusion_note          = fusion.get("fusion_note", "")
        overrides            = fusion.get("overrides_triggered", [])

        # 6. Save Prediction
        prediction = Predictions.objects.create(
            patient=patient,
            clinical_score=clinical_score,
            image_score=image_score,
            final_score=final_score,
            risk_level=risk_level,
            recommendation=recommendation,
            fusion_note=fusion_note,
            contributing_factors=json.dumps(contributing_factors),
            overrides_triggered=json.dumps(overrides),
            model_version='v1.0'
        )

        # 7. Return Response
        response_data = {
            'success':              True,
            'message':              'Prediction completed successfully',
            'patient_id':           patient.id,
            'prediction_id':        prediction.id,
            'clinical_score':       round(clinical_score, 4),
            'image_score':          round(image_score, 4) if image_score is not None else None,
            'final_score':          round(final_score, 4),
            'risk_level':           risk_level,
            'recommendation':       recommendation,
            'fusion_note':          fusion_note,
            'overrides_triggered':  overrides,
            'contributing_factors': contributing_factors,
        }

        if image_result:
            response_data['image_analysis'] = {
                'stroke_type':   image_result['stroke_type'],
                'confidence':    image_result['confidence'],
                'probabilities': image_result['probabilities'],
                'gradcam_url':   image_result.get('gradcam_url'),
            }

        return Response(response_data, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({'success': False, 'message': 'Prediction failed', 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def predictions_list(request):
    predictions = Predictions.objects.select_related('patient').all()
    serializer  = PredictionSerializer(predictions, many=True)
    return Response({'success': True, 'count': len(serializer.data), 'data': serializer.data})


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def prediction_detail(request, pk):
    try:
        prediction = Predictions.objects.get(pk=pk)
        serializer = PredictionSerializer(prediction)
        return Response({'success': True, 'data': serializer.data})
    except Predictions.DoesNotExist:
        return Response({'success': False, 'message': 'Prediction not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def patient_predictions(request, patient_id):
    try:
        patient     = Patients.objects.get(pk=patient_id)
        predictions = Predictions.objects.filter(patient=patient)
        serializer  = PredictionSerializer(predictions, many=True)
        return Response({
            'success': True,
            'patient': PatientSerializer(patient).data,
            'predictions_count': len(serializer.data),
            'predictions': serializer.data
        })
    except Patients.DoesNotExist:
        return Response({'success': False, 'message': 'Patient not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def high_risk_patients(request):
    predictions = Predictions.objects.filter(risk_level='High').select_related('patient').order_by('-final_score')
    serializer  = PredictionSerializer(predictions, many=True)
    return Response({'success': True, 'count': len(serializer.data), 'data': serializer.data})


# ══════════════════════════════════════════
# Dashboard & Analytics APIs
# ══════════════════════════════════════════

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def dashboard_overview(request):
    total_patients    = Patients.objects.count()
    total_predictions = Predictions.objects.count()
    high_risk         = Predictions.objects.filter(risk_level='High').count()
    medium_risk       = Predictions.objects.filter(risk_level='Medium').count()
    low_risk          = Predictions.objects.filter(risk_level='Low').count()

    from django.db.models import Avg
    avg_scores = Predictions.objects.aggregate(
        avg_clinical=Avg('clinical_score'),
        avg_image=Avg('image_score'),
        avg_final=Avg('final_score')
    )

    return Response({
        'success': True,
        'statistics': {
            'total_patients':    total_patients,
            'total_predictions': total_predictions,
            'risk_distribution': {'high': high_risk, 'medium': medium_risk, 'low': low_risk},
            'average_scores': {
                'clinical': round(avg_scores['avg_clinical'] or 0, 2),
                'image':    round(avg_scores['avg_image']    or 0, 2),
                'final':    round(avg_scores['avg_final']    or 0, 2)
            }
        }
    })


# ══════════════════════════════════════════════════════════
# DB Views Endpoints
# ══════════════════════════════════════════════════════════

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def all_patients_view(request):
    try:
        patients = AllPatientsView.objects.all()
        data = list(patients.values('patient_id', 'full_name', 'age', 'sex', 'predictions_count', 'last_risk', 'registered_at'))
        return Response({'success': True, 'count': len(data), 'data': data})
    except Exception as e:
        return Response({'success': False, 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def all_predictions_view_api(request):
    try:
        predictions = AllPredictionsView.objects.all()
        data = list(predictions.values('full_name', 'age', 'sex', 'final_score', 'clinical_score', 'image_score', 'contributing_factors'))
        for row in data:
            cf = row.get('contributing_factors')
            if cf:
                try:
                    row['contributing_factors'] = json.loads(cf)
                except Exception:
                    pass
        return Response({'success': True, 'count': len(data), 'data': data})
    except Exception as e:
        return Response({'success': False, 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def db_counts(request):
    try:
        patients_count    = PatientsCountView.objects.first()
        predictions_count = PredictionsCountView.objects.first()
        return Response({
            'success': True,
            'total_patients':    patients_count.total_patients       if patients_count    else 0,
            'total_predictions': predictions_count.total_predictions if predictions_count else 0,
        })
    except Exception as e:
        return Response({'success': False, 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def db_search_patients(request):
    query = request.GET.get('q', '').strip()
    if not query:
        return Response({'success': False, 'message': 'اكتب اسم للبحث عنه في query param q'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        results = search_patient_by_name(query)
        return Response({'success': True, 'count': len(results), 'data': results})
    except Exception as e:
        return Response({'success': False, 'message': f'خطأ في الـ DB function: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ══════════════════════════════════════════
# Prescription APIs  ← الجديد
# ══════════════════════════════════════════

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def prescription_create(request):
    """
    POST /api/prescriptions/create/
    Body: { "patient_id": 2, "prescription": "Aspirin 100mg daily" }
    """
    patient_id       = request.data.get('patient_id')
    prescription_txt = request.data.get('prescription', '').strip()

    if not patient_id:
        return Response({'success': False, 'message': 'patient_id مطلوب'}, status=status.HTTP_400_BAD_REQUEST)
    if not prescription_txt:
        return Response({'success': False, 'message': 'prescription مطلوب'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        patient = Patients.objects.get(pk=patient_id)
    except Patients.DoesNotExist:
        return Response({'success': False, 'message': 'Patient not found'}, status=status.HTTP_404_NOT_FOUND)

    rx = Prescription.objects.create(
        patient=patient,
        doc=request.user,
        prescription=prescription_txt
    )

    return Response({
        'success': True,
        'message': 'تم حفظ الروشتة بنجاح',
        'data': PrescriptionSerializer(rx).data
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def prescription_by_patient(request, patient_id):
    """GET /api/prescriptions/patient/{id}/"""
    try:
        patient = Patients.objects.get(pk=patient_id)
    except Patients.DoesNotExist:
        return Response({'success': False, 'message': 'Patient not found'}, status=status.HTTP_404_NOT_FOUND)

    prescriptions = Prescription.objects.filter(patient=patient)
    serializer    = PrescriptionSerializer(prescriptions, many=True)
    return Response({
        'success': True,
        'patient': PatientSerializer(patient).data,
        'count':   len(serializer.data),
        'data':    serializer.data
    })


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def prescription_detail(request, pk):
    """GET /api/prescriptions/{id}/"""
    try:
        rx = Prescription.objects.get(pk=pk)
        return Response({'success': True, 'data': PrescriptionSerializer(rx).data})
    except Prescription.DoesNotExist:
        return Response({'success': False, 'message': 'Prescription not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['PUT'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def prescription_update(request, pk):
    """PUT /api/prescriptions/{id}/update/ — الدكتور اللي كتبها بس يقدر يعدلها"""
    try:
        rx = Prescription.objects.get(pk=pk)
    except Prescription.DoesNotExist:
        return Response({'success': False, 'message': 'Prescription not found'}, status=status.HTTP_404_NOT_FOUND)

    if rx.doc != request.user:
        return Response({'success': False, 'message': 'مش مسموحلك تعدل روشتة دكتور تاني'}, status=status.HTTP_403_FORBIDDEN)

    new_text = request.data.get('prescription', '').strip()
    if not new_text:
        return Response({'success': False, 'message': 'prescription مطلوب'}, status=status.HTTP_400_BAD_REQUEST)

    rx.prescription = new_text
    rx.save()
    return Response({'success': True, 'message': 'تم تعديل الروشتة', 'data': PrescriptionSerializer(rx).data})


@api_view(['DELETE'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def prescription_delete(request, pk):
    """DELETE /api/prescriptions/{id}/delete/ — الدكتور اللي كتبها بس يقدر يحذفها"""
    try:
        rx = Prescription.objects.get(pk=pk)
    except Prescription.DoesNotExist:
        return Response({'success': False, 'message': 'Prescription not found'}, status=status.HTTP_404_NOT_FOUND)

    if rx.doc != request.user:
        return Response({'success': False, 'message': 'مش مسموحلك تحذف روشتة دكتور تاني'}, status=status.HTTP_403_FORBIDDEN)

    rx.delete()
    return Response({'success': True, 'message': 'تم حذف الروشتة'}, status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def prescription_my(request):
    """GET /api/prescriptions/my/ — الدكتور يشوف الروشتات اللي هو كتبها"""
    prescriptions = Prescription.objects.filter(doc=request.user)
    serializer    = PrescriptionSerializer(prescriptions, many=True)
    return Response({'success': True, 'count': len(serializer.data), 'data': serializer.data})


# ══════════════════════════════════════════
# Health Check
# ══════════════════════════════════════════

@api_view(['GET'])
def health_check(request):
    return Response({
        'success': True,
        'message': 'Backend is running',
        'models_loaded': {
            'clinical': MLService._clinical_model is not None,
            'image':    MLService._image_model    is not None,
            'fusion':   'dynamic_fusion_v2 (rule-based, always active)',
        }
    })

# ══════════════════════════════════════════════════════════
# NEW: Self-Evolving System — Endpoints
# 3 endpoints جدد، مش بيأثروا على أي حاجة موجودة
# ══════════════════════════════════════════════════════════

from .models import ConfirmedCase, ModelVersion


@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def confirm_diagnosis(request, prediction_id):
    """
    POST /api/self-evolving/confirm/{prediction_id}/

    الدكتور يأكد (أو يصحح) تشخيص النظام.
    بعد التأكيد بيتحقق تلقائي لو حان وقت الـ retrain.

    Body:
    {
        "confirmed_label": "High"   ← أو "Medium" أو "Low"
    }
    """
    confirmed_label = request.data.get('confirmed_label', '').strip()
    if confirmed_label not in ['High', 'Medium', 'Low']:
        return Response(
            {'success': False, 'message': 'confirmed_label لازم يكون High أو Medium أو Low'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # جيب التنبؤ الأصلي
    try:
        prediction = Predictions.objects.get(pk=prediction_id)
    except Predictions.DoesNotExist:
        return Response(
            {'success': False, 'message': 'Prediction not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    patient = prediction.patient

    # جيب آخر بيانات سريرية للمريض
    clinical = ClinicalData.objects.filter(patient=patient).order_by('-created_at').first()
    if not clinical:
        return Response(
            {'success': False, 'message': 'No clinical data found for this patient'},
            status=status.HTTP_404_NOT_FOUND
        )

    # احفظ الحالة المؤكدة
    ConfirmedCase.objects.create(
        patient                = patient,
        prediction             = prediction,
        age                    = patient.age,
        sex                    = patient.sex,
        bmi                    = clinical.bmi,
        smoking                = clinical.smoking,
        heartdisease           = clinical.heartdisease,
        diabetic               = clinical.diabetic,
        kidneydisease          = clinical.kidneydisease,
        diffwalking            = clinical.diffwalking,
        genhealth              = clinical.genhealth,
        sleeptime              = clinical.sleeptime,
        physicalhealth         = clinical.physicalhealth,
        mentalhealth           = clinical.mentalhealth,
        system_prediction      = prediction.risk_level,
        system_confidence      = prediction.final_score,
        doctor_confirmed_label = confirmed_label,
        confirmed_by           = request.user,
    )

    # تحقق لو حان وقت الـ retrain
    retrain_result = MLService.check_and_retrain()

    return Response({
        'success':        True,
        'message':        'Diagnosis confirmed successfully',
        'confirmed_label': confirmed_label,
        'retrain_status': retrain_result,
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def model_registry(request):
    """
    GET /api/self-evolving/registry/

    يجيب سجل كل versions الموديل.
    يبيّن الـ active version والـ accuracy لكل version.
    """
    try:
        versions    = ModelVersion.objects.all().order_by('-trained_at')
        active      = versions.filter(is_active=True).first()

        versions_data = []
        for v in versions:
            versions_data.append({
                'version_name': v.version_name,
                'accuracy':     round(v.accuracy * 100, 2),
                'cases_count':  v.cases_count,
                'status':       v.status,
                'is_active':    v.is_active,
                'trained_at':   v.trained_at,
                'notes':        v.notes,
            })

        pending_cases = ConfirmedCase.objects.filter(used_in_training=False).count()

        return Response({
            'success':         True,
            'active_version':  active.version_name if active else 'v1 (original)',
            'pending_cases':   pending_cases,
            'retrain_threshold': MLService.RETRAIN_THRESHOLD,
            'cases_until_retrain': max(0, MLService.RETRAIN_THRESHOLD - pending_cases),
            'versions':        versions_data,
        })

    except Exception as e:
        return Response(
            {'success': False, 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def rollback_model(request):
    """
    POST /api/self-evolving/rollback/

    رجّع لـ version قديمة في حالة فيه مشكلة في الجديدة.

    Body:
    {
        "version_name": "v2"
    }
    """
    version_name = request.data.get('version_name', '').strip()
    if not version_name:
        return Response(
            {'success': False, 'message': 'version_name مطلوب'},
            status=status.HTTP_400_BAD_REQUEST
        )

    result = MLService.rollback_to_version(version_name)

    if result.get('status') == 'error':
        return Response(
            {'success': False, 'message': result.get('message')},
            status=status.HTTP_400_BAD_REQUEST
        )

    return Response({
        'success': True,
        'data':    result,
    })