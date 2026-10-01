from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
	FacultyViewSet,
	GroupViewSet,
	StudentViewSet,
	UserViewSet,
	hemis_authorize,
	hemis_callback,
	login,
	me,
)

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("students", StudentViewSet, basename="student")
router.register("groups", GroupViewSet, basename="group")
router.register("faculties", FacultyViewSet, basename="faculty")

urlpatterns = [
	path("login/", login),
	path("refresh/", TokenRefreshView.as_view()),
	path("me/", me),
	path("hemis/authorize/", hemis_authorize),
	path("hemis/callback/", hemis_callback),
] + router.urls
