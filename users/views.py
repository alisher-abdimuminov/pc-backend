from datetime import date

from django.contrib.auth.models import Permission, update_last_login
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .audit import audit_extra, log_action
from .hemis import HemisAuthError, HemisError, authenticate_hemis
from .models import AuditLog, User
from .permissions import PERMISSION_CODES, PERMISSIONS, Can, IsAdminRole, IsStaffRole, visible_groups
from .serializers import AuditLogSerializer, LoginSerializer, StaffSerializer, UserSerializer

HEMIS_ROLES = ("student", "teacher")


def _tokens(user: User, request) -> dict:
	refresh = RefreshToken.for_user(user)
	return {
		"access": str(refresh.access_token),
		"refresh": str(refresh),
		"user": UserSerializer(user, context={"request": request}).data,
	}


class LoginView(APIView):
	"""
	1. User db da bo'lsa va parol to'g'ri bo'lsa - classic login.
	2. Aks holda student/teacher uchun HEMIS orqali tekshiriladi va user yaratiladi/yangilanadi
	   (HEMIS da parol o'zgargan holat ham shu yerda yopiladi).
	Admin va boshqa rollar faqat classic login.
	Har bir urinish (muvaffaqiyatsizi ham) AuditLog'ga LOGIN sifatida yoziladi.
	"""

	permission_classes = (AllowAny,)
	authentication_classes = ()

	def _fail(self, login, user, detail, code, reason):
		log_action("LOGIN", user, {"success": False, "login": login, "reason": reason}, user=user)
		return Response({"detail": detail}, status=code)

	def _ok(self, user, request, via):
		update_last_login(None, user)
		log_action("LOGIN", user, {"success": True, "via": via}, user=user)
		return Response(_tokens(user, request))

	def post(self, request):
		serializer = LoginSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		login = serializer.validated_data["login"].strip()
		password = serializer.validated_data["password"]

		user = User.objects.filter(username=login).first()
		if user and user.check_password(password):
			if not user.is_active:
				return self._fail(login, user, "Foydalanuvchi bloklangan", status.HTTP_403_FORBIDDEN, "blocked")
			return self._ok(user, request, "password")

		if user and user.role not in HEMIS_ROLES:
			return self._fail(
				login, user, "Login yoki parol noto'g'ri", status.HTTP_401_UNAUTHORIZED, "wrong_password"
			)

		try:
			# bazada bor talaba/o'qituvchi - o'z roli bo'yicha, yo'q bo'lsa avval talaba, keyin o'qituvchi
			user = authenticate_hemis(login, password, roles=(user.role,) if user else HEMIS_ROLES)
		except HemisAuthError as e:
			return self._fail(login, user, str(e), status.HTTP_401_UNAUTHORIZED, "hemis_auth")
		except HemisError as e:
			return self._fail(login, user, str(e), status.HTTP_502_BAD_GATEWAY, "hemis_error")

		if not user.is_active:
			return self._fail(login, user, "Foydalanuvchi bloklangan", status.HTTP_403_FORBIDDEN, "blocked")
		return self._ok(user, request, "hemis")


class LogoutView(APIView):
	def post(self, request):
		log_action("LOGOUT", request.user)
		return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
	def get(self, request):
		return Response(UserSerializer(request.user, context={"request": request}).data)


class StudentListView(APIView):
	"""Talabalarni qidirish (jadval biriktirish va h.k. uchun): ?search=&group=<uuid>"""

	permission_classes = (Can("users.view_user"),)

	def get(self, request):
		students = User.objects.filter(role="student", group__in=visible_groups(request.user)).select_related(
			"group"
		)
		if search := request.query_params.get("search"):
			students = students.filter(Q(full_name__icontains=search) | Q(username__icontains=search))
		if group := request.query_params.get("group"):
			students = students.filter(group__uuid=group)
		return Response(
			[
				{
					"uuid": s.uuid,
					"username": s.username,
					"full_name": s.full_name,
					"group": s.group.name if s.group else None,
					"is_active": s.is_active,
				}
				for s in students.order_by("full_name")[:50]
			]
		)


# --- guruhga o'qituvchi biriktirish ---


class TeacherListView(APIView):
	"""O'qituvchilar ro'yxati (guruhga biriktirish uchun): ?search="""

	permission_classes = (Can("users.change_group"),)

	def get(self, request):
		teachers = User.objects.filter(role="teacher", is_active=True)
		if search := request.query_params.get("search", "").strip():
			teachers = teachers.filter(Q(full_name__icontains=search) | Q(username__icontains=search))
		return Response(
			[
				{
					"uuid": t.uuid,
					"username": t.username,
					"full_name": t.full_name or t.username,
					"groups_count": t.teaching_groups.count(),
				}
				for t in teachers.order_by("full_name")[:100]
			]
		)


class GroupTeacherSerializer(serializers.Serializer):
	teacher_uuid = serializers.UUIDField(allow_null=True)


class GroupTeacherView(APIView):
	"""Guruhga o'qituvchi biriktirish / olib tashlash (teacher_uuid=null). AuditLog - signal orqali."""

	permission_classes = (Can("users.change_group"),)

	def patch(self, request, uuid):
		group = get_object_or_404(visible_groups(request.user), uuid=uuid)
		serializer = GroupTeacherSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		teacher_uuid = serializer.validated_data["teacher_uuid"]
		teacher = (
			get_object_or_404(User, uuid=teacher_uuid, role="teacher", is_active=True) if teacher_uuid else None
		)
		group.teacher = teacher
		group.save(update_fields=["teacher", "updated_at"])
		return Response(
			{
				"uuid": group.uuid,
				"name": group.name,
				"teacher": {"uuid": teacher.uuid, "full_name": teacher.full_name} if teacher else None,
			}
		)


# --- talabani bloklash ---


class StudentStatusSerializer(serializers.Serializer):
	is_active = serializers.BooleanField()
	reason = serializers.CharField(max_length=1000, allow_blank=True, default="")
	attempt_uuid = serializers.UUIDField(required=False, allow_null=True)


class StudentStatusView(APIView):
	"""
	Talabani bloklash (shubhali urinish) yoki qayta faollashtirish.
	Bloklangan talaba tizimga kira olmaydi, mavjud tokenlari ham ishlamay qoladi (simplejwt is_active tekshiradi).
	Sabab AuditLog'ga yoziladi.
	"""

	permission_classes = (Can("users.change_user"),)

	def post(self, request, uuid):
		student = get_object_or_404(
			User.objects.filter(role="student", group__in=visible_groups(request.user)), uuid=uuid
		)
		serializer = StudentStatusSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		data = serializer.validated_data
		if not data["is_active"] and not data["reason"].strip():
			return Response({"reason": ["Bloklash sababini yozing"]}, status=status.HTTP_400_BAD_REQUEST)

		attempt = str(data["attempt_uuid"]) if data.get("attempt_uuid") else None
		with transaction.atomic(), audit_extra(reason=data["reason"], attempt=attempt):
			student.is_active = data["is_active"]
			student.save(update_fields=["is_active", "updated_at"])
		return Response({"uuid": student.uuid, "is_active": student.is_active})


class StudentStatusHistoryView(APIView):
	"""Talabaning bloklash/faollashtirish tarixi (AuditLog'dan)."""

	permission_classes = (Can("users.view_user"),)

	def get(self, request, uuid):
		student = get_object_or_404(
			User.objects.filter(role="student", group__in=visible_groups(request.user)), uuid=uuid
		)
		logs = AuditLog.objects.filter(
			content_type=ContentType.objects.get_for_model(User),
			object_id=str(student.pk),
			action="UPDATE",
			changes__has_key="is_active",
		).select_related("user")[:20]
		return Response(
			[
				{
					"is_active": log.changes["is_active"][1],
					"reason": log.changes.get("reason", ""),
					"by": (log.user.full_name or log.user.username) if log.user else None,
					"at": log.created_at,
				}
				for log in logs
			]
		)


# --- little xodimlar va ularning permission'lari (faqat admin) ---


class PermissionCatalogView(APIView):
	permission_classes = (IsAdminRole,)

	def get(self, request):
		return Response([{"code": code, "section": section, "label": label} for code, section, label in PERMISSIONS])


def _set_permissions(user: User, codes: list[str]):
	unknown = set(codes) - PERMISSION_CODES
	if unknown:
		raise ValidationError({"permissions": [f"Noma'lum permission: {', '.join(sorted(unknown))}"]})
	q = Q(pk__in=[])
	for code in codes:
		app_label, codename = code.split(".")
		q |= Q(content_type__app_label=app_label, codename=codename)
	old = sorted(user.get_all_permissions() & PERMISSION_CODES)
	user.user_permissions.set(Permission.objects.filter(q))
	new = sorted(codes)
	if old != new:
		# M2M o'zgarishi post_save signaliga tushmaydi - alohida yoziladi
		log_action("UPDATE", user, {"permissions": [old, new]})


class StaffListCreateView(generics.ListCreateAPIView):
	"""little roli xodimlari: ro'yxat va yangi xodim."""

	permission_classes = (IsAdminRole,)
	serializer_class = StaffSerializer
	pagination_class = None

	def get_queryset(self):
		qs = User.objects.filter(role="little").prefetch_related("user_permissions__content_type")
		if search := self.request.query_params.get("search", "").strip():
			qs = qs.filter(Q(full_name__icontains=search) | Q(username__icontains=search))
		return qs.order_by("full_name", "username")

	def perform_create(self, serializer):
		with transaction.atomic():
			user = serializer.save()
			_set_permissions(user, serializer.validated_data.get("permissions", []))


class StaffDetailView(generics.RetrieveUpdateAPIView):
	permission_classes = (IsAdminRole,)
	serializer_class = StaffSerializer
	lookup_field = "uuid"
	queryset = User.objects.filter(role="little")
	http_method_names = ("get", "patch")

	def perform_update(self, serializer):
		with transaction.atomic():
			user = serializer.save()
			if "permissions" in serializer.validated_data:
				# get_all_permissions keshini tozalash
				for attr in ("_perm_cache", "_user_perm_cache"):
					user.__dict__.pop(attr, None)
				_set_permissions(user, serializer.validated_data["permissions"])


# --- audit jurnal ---


class AuditPagination(PageNumberPagination):
	page_size = 30
	page_size_query_param = "page_size"
	max_page_size = 100


class AuditLogListView(generics.ListAPIView):
	"""
	Audit jurnal. Filtrlar: action, model (app_label.model), search (foydalanuvchi / obyekt),
	from, to (YYYY-MM-DD), user (uuid).
	"""

	permission_classes = (Can("users.view_auditlog"),)
	serializer_class = AuditLogSerializer
	pagination_class = AuditPagination

	def get_queryset(self):
		params = self.request.query_params
		qs = AuditLog.objects.select_related("user", "content_type")
		if action := params.get("action"):
			qs = qs.filter(action=action)
		if model := params.get("model"):
			app_label, _, name = model.partition(".")
			qs = qs.filter(content_type__app_label=app_label, content_type__model=name)
		if user := params.get("user"):
			qs = qs.filter(user__uuid=user)
		if search := params.get("search", "").strip():
			qs = qs.filter(
				Q(user__full_name__icontains=search)
				| Q(user__username__icontains=search)
				| Q(object_repr__icontains=search)
			)
		for key, lookup in (("from", "created_at__date__gte"), ("to", "created_at__date__lte")):
			if value := params.get(key):
				try:
					qs = qs.filter(**{lookup: date.fromisoformat(value)})
				except ValueError as e:
					raise ValidationError({key: "Sana formati: YYYY-MM-DD"}) from e
		return qs.order_by("-created_at")


class AuditFiltersView(APIView):
	permission_classes = (Can("users.view_auditlog"),)

	def get(self, request):
		from .audit import TRACKED_MODELS

		models_ = []
		for label in TRACKED_MODELS:
			app_label, name = label.split(".")
			ct = ContentType.objects.get_by_natural_key(app_label, name.lower())
			models_.append({"value": f"{app_label}.{name.lower()}", "label": str(ct.model_class()._meta.verbose_name)})
		return Response(
			{
				"actions": [{"value": v, "label": label} for v, label in AuditLog._meta.get_field("action").choices],
				"models": models_,
			}
		)
