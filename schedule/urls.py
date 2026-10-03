from django.urls import path

from . import views


urlpatterns = [
    path("", views.home, name="home"),
    path("week/<str:week_start>/", views.schedule, name="schedule"),
    path("week/<str:week_start>/assignment/<int:person_id>/<int:day>/", views.assignment_save, name="assignment_save"),
    path("week/<str:week_start>/clear/", views.schedule_clear, name="schedule_clear"),
    path("people/", views.people, name="people"),
    path("people/<int:person_id>/delete/", views.person_delete, name="person_delete"),
    path("branches/", views.branches, name="branches"),
    path("branches/<int:branch_id>/delete/", views.branch_delete, name="branch_delete"),
    path("analysis/", views.analysis, name="analysis"),
    path("analysis/unlock/", views.analysis_unlock, name="analysis_unlock"),
    path("exports/schedule/", views.schedule_export, name="schedule_export"),
    path("exports/analysis/", views.analysis_export, name="analysis_export"),
]
