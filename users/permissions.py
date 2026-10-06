"""
Ruxsatlar.

Har bir bo'lim Django permission kodi bilan himoyalanadi (masalan "attendance.add_location").
- admin       - hammasi
- little      - faqat admin bergan permission'lar (User.user_permissions). Hech narsa berilmasa - faqat bosh sahifa
- dean/teacher - ROLE_PERMISSIONS dagi standart to'plam (ko'rinadigan guruhlar visible_groups bilan cheklanadi)
- urinishlar (attendance.view_attendanceattempt) - faqat admin va shu ruxsat berilgan little
- student     - xodimlar bo'limiga kira olmaydi
"""

from rest_framework.permissions import BasePermission

from .models import Group

STAFF_ROLES = ("admin", "little", "dean", "teacher")

# little'ga berish mumkin bo'lgan permission'lar katalogi: (kod, bo'lim, amal)
PERMISSIONS = (
	("users.view_group", "Guruhlar", "Ko'rish"),
	("users.change_group", "Guruhlar", "O'qituvchi biriktirish"),
	("attendance.view_attendance", "Davomat", "Guruh davomati va hisobotlar"),
	("attendance.view_attendanceattempt", "Urinishlar", "Ko'rish"),
	("users.view_user", "Talabalar", "Qidirish va ko'rish"),
	("users.change_user", "Talabalar", "Bloklash / faollashtirish"),
	("attendance.view_schedule", "Jadvallar", "Ko'rish"),
	("attendance.add_schedule", "Jadvallar", "Qo'shish"),
	("attendance.change_schedule", "Jadvallar", "Tahrirlash"),
	("attendance.delete_schedule", "Jadvallar", "O'chirish"),
	("attendance.view_location", "Lokatsiyalar", "Ko'rish"),
	("attendance.add_location", "Lokatsiyalar", "Qo'shish"),
	("attendance.change_location", "Lokatsiyalar", "Tahrirlash"),
	("attendance.delete_location", "Lokatsiyalar", "O'chirish"),
	("assignments.view_assignment", "Topshiriqlar", "Ko'rish"),
	("users.view_auditlog", "Audit jurnal", "Ko'rish"),
)
PERMISSION_CODES = frozenset(code for code, _, _ in PERMISSIONS)

# o'qituvchi: faqat o'z guruhlari (visible_groups), ularning davomati ("keldi/kelmadi") va topshiriqlari.
# Topshiriq yaratish/baholash - IsTeacher bilan alohida (faqat o'zi yaratganlari).
_TEACHER = frozenset(
	{
		"users.view_group",
		"attendance.view_attendance",
		"assignments.view_assignment",
	}
)
# dekan: o'z fakulteti. Urinishlar (rasm, GPS, yuz masofasi) - yo'q: faqat admin va ruxsat berilgan little
_DEAN = frozenset(
	{
		"users.view_group",
		"users.change_group",
		"attendance.view_attendance",
		"users.view_user",
		"users.change_user",
		"attendance.view_schedule",
		"attendance.view_location",
		"assignments.view_assignment",
	}
)
ROLE_PERMISSIONS = {
	"teacher": _TEACHER,
	"dean": _DEAN,
}


def effective_permissions(user) -> set[str]:
	"""Foydalanuvchining katalog bo'yicha amaldagi permission'lari."""
	if not user.is_authenticated or not user.is_active:
		return set()
	role = getattr(user, "role", None)
	if role == "admin":
		return set(PERMISSION_CODES)
	if role == "little":
		return user.get_all_permissions() & PERMISSION_CODES
	return set(ROLE_PERMISSIONS.get(role, ()))


def user_can(user, perm: str) -> bool:
	return perm in effective_permissions(user)


def Can(*perms: str):  # noqa: N802 - DRF permission class fabrikasi
	"""Berilgan permission'lardan kamida bittasi bo'lsa ruxsat."""

	class _Can(BasePermission):
		def has_permission(self, request, view):
			granted = effective_permissions(request.user)
			return any(p in granted for p in perms)

	_Can.__name__ = f"Can({', '.join(perms)})"
	return _Can


def ModelPermission(model: str):  # noqa: N802
	"""HTTP metod bo'yicha model permission'i: GET - view, POST - add, PUT/PATCH - change, DELETE - delete."""
	app_label, name = model.split(".")
	actions = {
		"GET": "view",
		"HEAD": "view",
		"OPTIONS": "view",
		"POST": "add",
		"PUT": "change",
		"PATCH": "change",
		"DELETE": "delete",
	}

	class _ModelPermission(BasePermission):
		def has_permission(self, request, view):
			action = actions.get(request.method)
			return bool(action) and user_can(
				request.user, f"{app_label}.{action}_{name}"
			)

	_ModelPermission.__name__ = f"ModelPermission({model})"
	return _ModelPermission


class IsStudent(BasePermission):
	def has_permission(self, request, view):
		return request.user.role == "student"


class IsTeacher(BasePermission):
	def has_permission(self, request, view):
		return request.user.role == "teacher"


class IsStaffRole(BasePermission):
	"""Xodimlar bo'limi (bosh sahifa) - o'qituvchi, dekan, admin, little."""

	def has_permission(self, request, view):
		return request.user.role in STAFF_ROLES


class IsAdminRole(BasePermission):
	def has_permission(self, request, view):
		return request.user.role == "admin"


def visible_groups(user):
	"""Rolga qarab foydalanuvchi ko'ra oladigan guruhlar."""
	groups = Group.objects.select_related("faculty", "teacher").order_by("name")
	if user.role in ("admin", "little"):
		return groups
	if user.role == "dean":
		return (
			groups.filter(faculty_id=user.faculty_id)
			if user.faculty_id
			else groups.none()
		)
	if user.role == "teacher":
		return groups.filter(teacher=user)
	return groups.none()
