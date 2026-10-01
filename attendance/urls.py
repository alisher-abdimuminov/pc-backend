from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
	AttendanceAttemptViewSet,
	AttendanceMonitoringViewSet,
	LocationViewSet,
	ScheduleViewSet,
	check,
	today,
)

router = DefaultRouter()
router.register("locations", LocationViewSet, basename="location")
router.register("schedules", ScheduleViewSet, basename="schedule")
router.register("monitoring", AttendanceMonitoringViewSet, basename="monitoring")
router.register("attempts", AttendanceAttemptViewSet, basename="attempt")


urlpatterns = [
	path(
		"today/",
		today,
		name="attendance-today",
	),
	path(
		"check/",
		check,
		name="attendance-check",
	),
]

urlpatterns += router.urls
