from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("locations", views.LocationViewSet, basename="location")
router.register("schedules", views.ScheduleViewSet, basename="schedule")

urlpatterns = [
	# talaba
	path("today/", views.TodayView.as_view()),
	path("location/", views.LocationCheckView.as_view()),
	path("check-in/", views.CheckInView.as_view()),
	path("my/schedules/", views.MySchedulesView.as_view()),
	# o'qituvchi / dekan / admin
	path("groups/", views.GroupListView.as_view()),
	path("groups/<uuid:uuid>/", views.GroupAttendanceView.as_view()),
	path("groups/<uuid:uuid>/report/", views.GroupReportView.as_view()),
	path("students/<uuid:uuid>/", views.StudentAttendancesView.as_view()),
	path("attempts/", views.AttemptListView.as_view()),
	path("attempts/filters/", views.AttemptFiltersView.as_view()),
	path("dashboard/", views.DashboardView.as_view()),
	*router.urls,
]
