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

from .models import Patients, ClinicalData, CtImages, Predictions
from .serializers import (
    PatientSerializer,
    ClinicalDataSerializer,
    CtImageSerializer,
    PredictionSerializer,
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

    # ── Validation ──────────────────────────────
    if not username or not password:
        return Response({
            'success': False,
            'message': 'اسم المستخدم وكلمة المرور مطلوبان'
        }, status=status.HTTP_400_BAD_REQUEST)

    if len(password) < 8:
        return Response({
            'success': False,
            'message': 'كلمة المرور لازم تكون 8 حروف على الأقل'
        }, status=status.HTTP_400_BAD_REQUEST)

    if User.objects.filter(username=username).exists():
        return Response({
            'success': False,
            'message': 'اسم المستخدم ده موجود بالفعل'
        }, status=status.HTTP_400_BAD_REQUEST)

    if email and User.objects.filter(email=email).exists():
        return Response({
            'success': False,
            'message': 'الإيميل ده مسجل بالفعل'
        }, status=status.HTTP_400_BAD_REQUEST)

    # ── Create User ─────────────────────────────
    user = User.objects.create_user(
        username=username,
        password=password,
        email=email
    )

    token, _ = Token.objects.get_or_create(user=user)

    return Response({
        'success': True,
        'message': 'تم إنشاء الحساب بنجاح',
        'token': token.key,
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_staff': user.is_staff,
        }
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    """تسجيل الدخول وإرجاع Token"""
    username = request.data.get('username', '').strip()
    password = request.data.get('password', '').strip()

    if not username or not password:
        return Response({
            'success': False,
            'message': 'اسم المستخدم وكلمة المرور مطلوبان'
        }, status=status.HTTP_400_BAD_REQUEST)

    user = authenticate(username=username, password=password)

    if user is None:
        return Response({
            'success': False,
            'message': 'اسم المستخدم أو كلمة المرور غلط'
        }, status=status.HTTP_401_UNAUTHORIZED)

    if not user.is_active:
        return Response({
            'success': False,
            'message': 'الحساب موقوف'
        }, status=status.HTTP_403_FORBIDDEN)

    token, _ = Token.objects.get_or_create(user=user)

    return Response({
        'success': True,
        'message': 'تم تسجيل الدخول بنجاح',
        'token': token.key,
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_staff': user.is_staff,
        }
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


# ================================
# Patient Management APIs
# ================================

@api_view(['GET', 'POST'])
def patients_list(request):
    if request.method == 'GET':
        patients = Patients.objects.all()
        serializer = PatientSerializer(patients, many=True)
        return Response({
            'success': True,
            'count': len(serializer.data),
            'data': serializer.data
        })

    elif request.method == 'POST':
        serializer = PatientSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'message': 'Patient created successfully',
                'data': serializer.data
            }, status=status.HTTP_201_CREATED)

        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
def patient_detail(request, pk):
    try:
        patient = Patients.objects.get(pk=pk)
    except Patients.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Patient not found'
        }, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = PatientSerializer(patient)
        clinical_data = ClinicalData.objects.filter(patient=patient)
        ct_scans = CtImages.objects.filter(patient=patient)
        predictions = Predictions.objects.filter(patient=patient)

        return Response({
            'success': True,
            'patient': serializer.data,
            'clinical_records': ClinicalDataSerializer(clinical_data, many=True).data,
            'ct_scans': CtImageSerializer(ct_scans, many=True).data,
            'predictions': PredictionSerializer(predictions, many=True).data
        })

    elif request.method == 'PUT':
        serializer = PatientSerializer(patient, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'message': 'Patient updated successfully',
                'data': serializer.data
            })

        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        patient.delete()
        return Response({
            'success': True,
            'message': 'Patient deleted successfully'
        }, status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
def search_patients(request):
    query = request.GET.get('q', '')

    if not query:
        return Response({
            'success': False,
            'message': 'Search query is required'
        }, status=status.HTTP_400_BAD_REQUEST)

    patients = Patients.objects.filter(full_name__icontains=query)
    serializer = PatientSerializer(patients, many=True)

    return Response({
        'success': True,
        'count': len(serializer.data),
        'data': serializer.data
    })


# ================================
# Prediction API
# ================================

@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def make_prediction(request):
    try:
        # Validate input
        input_serializer = PredictionInputSerializer(data=request.data)
        if not input_serializer.is_valid():
            return Response({
                'success': False,
                'errors': input_serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        data = input_serializer.validated_data

        # 1. Get or Create Patient
        patient_id = data.get('patient_id')

        if patient_id:
            try:
                patient = Patients.objects.get(pk=patient_id)
            except Patients.DoesNotExist:
                return Response({
                    'success': False,
                    'message': f'Patient with ID {patient_id} not found'
                }, status=status.HTTP_404_NOT_FOUND)
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
        image_score = None
        ct_image_record = None

        ct_scan = request.FILES.get('ct_scan')
        if ct_scan:
            file_name = f"patient_{patient.id}_{ct_scan.name}"
            file_path = default_storage.save(f"ct_scans/{file_name}", ContentFile(ct_scan.read()))

            ct_image_record = CtImages.objects.create(
                patient=patient,
                image_path=file_path
            )

            ct_scan.seek(0)
            image_score = MLService.predict_image(ct_scan)
        # FIX: removed "else: image_score = clinical_score"
        # image_score stays None when no CT scan → fusion handles it correctly

        # 5. Run Fusion — use fusion results directly (don't override below)
        fusion = MLService.predict_fusion(
            clinical_score,
            image_score,
            request.data  # raw data for rule-based checks (BMI, HeartDisease keys)
        )

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
        return Response({
            'success': True,
            'message': 'Prediction completed successfully',
            'patient_id': patient.id,
            'prediction_id': prediction.id,
            'clinical_score': round(clinical_score, 4),
            'image_score': round(image_score, 4) if image_score is not None else None,
            'final_score': round(final_score, 4),
            'risk_level': risk_level,
            'recommendation': recommendation,
            'fusion_note': fusion_note,
            'overrides_triggered': overrides,
            'contributing_factors': contributing_factors
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({
            'success': False,
            'message': 'Prediction failed',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def predictions_list(request):
    predictions = Predictions.objects.select_related('patient').all()
    serializer = PredictionSerializer(predictions, many=True)

    return Response({
        'success': True,
        'count': len(serializer.data),
        'data': serializer.data
    })


@api_view(['GET'])
def prediction_detail(request, pk):
    try:
        prediction = Predictions.objects.get(pk=pk)
        serializer = PredictionSerializer(prediction)

        return Response({
            'success': True,
            'data': serializer.data
        })

    except Predictions.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Prediction not found'
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
def patient_predictions(request, patient_id):
    try:
        patient = Patients.objects.get(pk=patient_id)
        predictions = Predictions.objects.filter(patient=patient)
        serializer = PredictionSerializer(predictions, many=True)

        return Response({
            'success': True,
            'patient': PatientSerializer(patient).data,
            'predictions_count': len(serializer.data),
            'predictions': serializer.data
        })

    except Patients.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Patient not found'
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
def high_risk_patients(request):
    predictions = Predictions.objects.filter(
        risk_level='High'
    ).select_related('patient').order_by('-final_score')

    serializer = PredictionSerializer(predictions, many=True)

    return Response({
        'success': True,
        'count': len(serializer.data),
        'data': serializer.data
    })


# ================================
# Dashboard & Analytics APIs
# ================================

@api_view(['GET'])
def dashboard_overview(request):
    total_patients = Patients.objects.count()
    total_predictions = Predictions.objects.count()

    high_risk   = Predictions.objects.filter(risk_level='High').count()
    medium_risk = Predictions.objects.filter(risk_level='Medium').count()
    low_risk    = Predictions.objects.filter(risk_level='Low').count()

    from django.db.models import Avg
    avg_scores = Predictions.objects.aggregate(
        avg_clinical=Avg('clinical_score'),
        avg_image=Avg('image_score'),
        avg_final=Avg('final_score')
    )

    return Response({
        'success': True,
        'statistics': {
            'total_patients': total_patients,
            'total_predictions': total_predictions,
            'risk_distribution': {
                'high': high_risk,
                'medium': medium_risk,
                'low': low_risk
            },
            'average_scores': {
                'clinical': round(avg_scores['avg_clinical'] or 0, 2),
                'image':    round(avg_scores['avg_image']    or 0, 2),
                'final':    round(avg_scores['avg_final']    or 0, 2)
            }
        }
    })


@api_view(['GET'])
def health_check(request):
    return Response({
        'success': True,
        'message': 'Backend is running',
        'models_loaded': {
            'clinical': MLService._clinical_model is not None,
            'image':    MLService._image_model    is not None,
            'fusion':   MLService._fusion_model   is not None
        }
    })