from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
	AuditFiltersView,
	AuditLogListView,
	GroupTeacherView,
	LoginView,
	LogoutView,
	MeView,
	PermissionCatalogView,
	StaffDetailView,
	StaffListCreateView,
	StudentListView,
	StudentStatusHistoryView,
	StudentStatusView,
	TeacherListView,
)

urlpatterns = [
	path("login/", LoginView.as_view()),
	path("refresh/", TokenRefreshView.as_view()),
	path("logout/", LogoutView.as_view()),
	path("me/", MeView.as_view()),
	path("permissions/", PermissionCatalogView.as_view()),
	path("staff/", StaffListCreateView.as_view()),
	path("staff/<uuid:uuid>/", StaffDetailView.as_view()),
	path("audit-logs/", AuditLogListView.as_view()),
	path("audit-logs/filters/", AuditFiltersView.as_view()),
	path("students/", StudentListView.as_view()),
	path("students/<uuid:uuid>/status/", StudentStatusView.as_view()),
	path("students/<uuid:uuid>/status/history/", StudentStatusHistoryView.as_view()),
	path("teachers/", TeacherListView.as_view()),
	path("groups/<uuid:uuid>/teacher/", GroupTeacherView.as_view()),
]
