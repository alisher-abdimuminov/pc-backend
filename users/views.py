from django.contrib.admin import filters
from django.contrib.auth import authenticate
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.filters import SearchFilter
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import Faculty, Group, User
from users.permissions import IsAdmin, IsTeacher

from .hemis import get_client, sync_hemis_user
from .serializers import FacultySerializer, GroupSerializer, UserSerializer


def tokens_for(user):
	if not user.is_active:
		return Response({"error": "Hisobingiz muzlatilgan"})
	refresh = RefreshToken.for_user(user)
	return {"access": str(refresh.access_token), "refresh": str(refresh)}


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
	user = authenticate(
		username=request.data.get("username"), password=request.data.get("password")
	)
	if not user:
		return Response({"detail": "Username yoki parol noto'g'ri"}, status=400)
	return Response(
		{
			"user": UserSerializer(user, context={"request": request}).data,
			"tokens": tokens_for(user),
		}
	)


@api_view(["GET"])
@permission_classes([AllowAny])
def hemis_authorize(request):
	kind = request.query_params.get("type", "student")
	if kind not in {"student", "teacher"}:
		return Response(
			{"detail": "type student yoki teacher bo'lishi kerak"}, status=400
		)
	return Response({"authorize_url": get_client(kind).authorization_url()})


@api_view(["POST"])
@permission_classes([AllowAny])
def hemis_callback(request):
	code = request.data.get("code")
	kind = request.data.get("type", "student")
	if not code or kind not in {"student", "teacher"}:
		return Response({"detail": "code va to'g'ri type majburiy"}, status=400)
	try:
		client = get_client(kind)
		token = client.get_access_token(code)
		details = client.get_user_details(token)
		user = sync_hemis_user(details, kind)
	except Exception as exc:
		return Response({"detail": str(exc)}, status=400)
	return Response(
		{
			"user": UserSerializer(user, context={"request": request}).data,
			"tokens": tokens_for(user),
		}
	)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
	return Response(UserSerializer(request.user, context={"request": request}).data)


class GroupViewSet(viewsets.ModelViewSet):
	lookup_field = "uuid"
	serializer_class = GroupSerializer
	permission_classes = (IsTeacher | IsAdmin,)
	search_fields = ("name",)
	filter_backends = (SearchFilter,)

	def get_queryset(self):
		u = self.request.user
		qs = Group.objects.select_related("teacher").all().order_by("name")
		if u.role == "teacher":
			return qs.filter(teacher=u)
		if u.role == "student":
			return qs.filter(pk=u.group_id)
		return qs


class FacultyViewSet(viewsets.ModelViewSet):
	lookup_field = "uuid"
	queryset = Faculty.objects.all().order_by("name")
	serializer_class = FacultySerializer
	permission_classes = (IsAdmin,)
	search_fields = ("name",)
	filter_backends = (SearchFilter,)


class UserViewSet(viewsets.ModelViewSet):
	lookup_field = "uuid"
	serializer_class = UserSerializer
	permission_classes = (IsAdmin,)
	search_fields = ("username", "full_name", "group__name")
	filter_backends = (SearchFilter,)
	http_method_names = ("get", "patch", "head", "options")

	def get_queryset(self):
		queryset = (
			User.objects.select_related("group")
			.filter(
				role__in=[
					"student",
					"teacher",
				]
			)
			.order_by(
				"full_name",
				"username",
			)
		)

		user_type = self.request.query_params.get("type")

		if user_type == "teacher":
			return queryset.filter(role="teacher")

		if user_type in [
			"student",
			"talaba",
		]:
			return queryset.filter(role="student")

		return queryset


class StudentViewSet(viewsets.ReadOnlyModelViewSet):
	serializer_class = UserSerializer
	permission_classes = (IsTeacher | IsAdmin,)

	def get_queryset(self):
		qs = (
			User.objects.filter(role="student")
			.select_related("group")
			.order_by("full_name")
		)
		u = self.request.user
		if u.role == "teacher":
			qs = qs.filter(group__teacher=u)
		g_uuid = self.request.query_params.get("group")
		return qs.filter(group__uuid=g_uuid) if g_uuid else qs
