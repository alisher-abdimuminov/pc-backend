from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("assignments", views.AssignmentViewSet, basename="assignment")
router.register("submissions", views.SubmissionViewSet, basename="submission")

urlpatterns = router.urls
