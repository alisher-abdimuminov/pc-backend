from rest_framework.routers import DefaultRouter

from .views import (
	AssignmentViewSet,
	StudentAssignmentViewSet,
	StudentSubmissionViewSet,
	SubmissionViewSet,
)

router = DefaultRouter()

router.register(
	"student-submissions",
	StudentSubmissionViewSet,
	basename="student-submissions",
)

router.register(
	"student",
	StudentAssignmentViewSet,
	basename="student-assignments",
)

router.register(
	"submissions",
	SubmissionViewSet,
	basename="submissions",
)

router.register(
	"",
	AssignmentViewSet,
	basename="assignments",
)

urlpatterns = router.urls
