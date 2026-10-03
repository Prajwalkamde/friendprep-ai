from django.urls import path

from . import views

app_name = "interview"

urlpatterns = [
    path("", views.home, name="home"),
    path("setup/", views.setup, name="setup"),
    path("session/<int:session_id>/", views.interview, name="interview"),
    path("session/<int:session_id>/submit/", views.submit_answer, name="submit_answer"),
    path("session/<int:session_id>/result/", views.result, name="result"),
]
