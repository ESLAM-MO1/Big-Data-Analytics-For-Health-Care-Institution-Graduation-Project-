from django.urls import path
from . import views

urlpatterns = [
    # ── Auth ──────────────────────────────────────────
    path('auth/register/', views.register_view, name='register'),
    path('auth/login/',    views.login_view,    name='login'),
    path('auth/logout/',   views.logout_view,   name='logout'),

    # ── Health Check ──────────────────────────────────
    path('health/', views.health_check, name='health_check'),

    # ── Patient Management ────────────────────────────
    path('patients/',          views.patients_list,   name='patients_list'),
    path('patients/search/',   views.search_patients, name='search_patients'),
    path('patients/<int:pk>/', views.patient_detail,  name='patient_detail'),

    # ── Predictions ───────────────────────────────────
    path('predict/',                              views.make_prediction,     name='make_prediction'),
    path('predictions/',                          views.predictions_list,    name='predictions_list'),
    path('predictions/high-risk/',                views.high_risk_patients,  name='high_risk_patients'),
    path('predictions/<int:pk>/',                 views.prediction_detail,   name='prediction_detail'),
    path('predictions/patient/<int:patient_id>/', views.patient_predictions, name='patient_predictions'),

    # ── Dashboard ─────────────────────────────────────
    path('dashboard/overview/', views.dashboard_overview, name='dashboard_overview'),

    # ── DB Views (PostgreSQL Views & Functions) ───────
    path('db/patients/',         views.all_patients_view,        name='db_all_patients'),
    path('db/patients/search/',  views.db_search_patients,       name='db_search_patients'),
    path('db/predictions/',      views.all_predictions_view_api, name='db_all_predictions'),
    path('db/counts/',           views.db_counts,                name='db_counts'),

    # ── Prescriptions ← الجديد ────────────────────────
    path('prescriptions/create/',                    views.prescription_create,     name='prescription_create'),
    path('prescriptions/my/',                        views.prescription_my,         name='prescription_my'),
    path('prescriptions/patient/<int:patient_id>/',  views.prescription_by_patient, name='prescription_by_patient'),
    path('prescriptions/<int:pk>/',                  views.prescription_detail,     name='prescription_detail'),
    path('prescriptions/<int:pk>/update/',           views.prescription_update,     name='prescription_update'),
    path('prescriptions/<int:pk>/delete/',           views.prescription_delete,     name='prescription_delete'),

    # ── NEW: Self-Evolving System ──────────────────────────
    path('self-evolving/confirm/<int:prediction_id>/', views.confirm_diagnosis, name='confirm_diagnosis'),
    path('self-evolving/registry/',                    views.model_registry,    name='model_registry'),
    path('self-evolving/rollback/',                    views.rollback_model,    name='rollback_model'),
]