from django.urls import path
from . import views

app_name = "tracker"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("jobs/", views.job_list, name="job_list"),
    path("jobs/<str:referenznummer>/", views.job_detail, name="job_detail"),
    path("jobs/<str:referenznummer>/apply/", views.mark_applied, name="mark_applied"),\n    path("jobs/<str:referenznummer>/save/", views.toggle_saved, name="toggle_saved"),
    path("jobs/<str:referenznummer>/status/", views.set_status, name="set_status"),
    path("jobs/<str:referenznummer>/document/", views.generate_document, name="generate_document"),
    path("applications/", views.application_list, name="application_list"),
    path("analytics/", views.analytics, name="analytics"),
    path("map/", views.map_view, name="map_view"),
    path("emails/", views.email_list, name="email_list"),
    path("settings/", views.settings_view, name="settings"),
    path("settings/blacklist/<int:pk>/delete/", views.delete_blacklist_entry, name="delete_blacklist_entry"),\n    path("tasks/start/", views.start_task, name="start_task"),\n    path("tasks/<int:pk>/", views.task_status, name="task_status"),
]