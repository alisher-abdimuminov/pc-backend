from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
	def has_permission(self, request, view):
		return bool(request.user.is_authenticated and request.user.role == "admin")


class IsDean(BasePermission):
	def has_permission(self, request, view):
		return bool(request.user.is_authenticated and request.user.role == "dean")


class IsTeacher(BasePermission):
	def has_permission(self, request, view):
		print(request.user.role)
		return bool(request.user.is_authenticated and request.user.role == "teacher")


class IsStudent(BasePermission):
	def has_permission(self, request, view):
		return bool(request.user.is_authenticated and request.user.role == "student")
