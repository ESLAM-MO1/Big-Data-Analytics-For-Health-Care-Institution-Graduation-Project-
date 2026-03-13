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
    path('patients/',              views.patients_list,   name='patients_list'),
    path('patients/search/',       views.search_patients, name='search_patients'),
    path('patients/<int:pk>/',     views.patient_detail,  name='patient_detail'),

    # ── Predictions ───────────────────────────────────
    path('predict/',                                views.make_prediction,     name='make_prediction'),
    path('predictions/',                            views.predictions_list,    name='predictions_list'),
    path('predictions/high-risk/',                  views.high_risk_patients,  name='high_risk_patients'),
    path('predictions/<int:pk>/',                   views.prediction_detail,   name='prediction_detail'),
    path('predictions/patient/<int:patient_id>/',   views.patient_predictions, name='patient_predictions'),

    # ── Dashboard ─────────────────────────────────────
    path('dashboard/overview/', views.dashboard_overview, name='dashboard_overview'),
]