from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from users.permissions import IsStudent, IsTeacher

from .models import Assignment, Submission
from .serializers import (
	AssignmentSerializer,
	GradeSubmissionSerializer,
	StudentAssignmentSerializer,
	StudentSubmissionSerializer,
	SubmissionSerializer,
)


class AssignmentViewSet(viewsets.ModelViewSet):
	serializer_class = AssignmentSerializer
	permission_classes = (IsTeacher,)

	filter_backends = (SearchFilter,)

	search_fields = (
		"title",
		"description",
		"groups__name",
	)

	lookup_field = "uuid"

	def get_queryset(self):
		return (
			Assignment.objects.filter(teacher=self.request.user)
			.prefetch_related("groups")
			.order_by("-created_at")
			.distinct()
		)

	def perform_create(
		self,
		serializer,
	):
		serializer.save(teacher=self.request.user)


class SubmissionViewSet(viewsets.ReadOnlyModelViewSet):
	serializer_class = SubmissionSerializer
	permission_classes = (IsTeacher,)

	filter_backends = (SearchFilter,)

	search_fields = (
		"student__full_name",
		"student__username",
	)

	lookup_field = "uuid"

	def get_queryset(self):
		qs = (
			Submission.objects.filter(assignment__teacher=self.request.user)
			.select_related(
				"assignment",
				"student",
				"graded_by",
			)
			.order_by("-submitted_at")
		)

		assignment_uuid = self.request.query_params.get("assignment")

		if assignment_uuid:
			qs = qs.filter(assignment__uuid=assignment_uuid)

		return qs

	@action(
		detail=True,
		methods=["post"],
		url_path="grade",
	)
	def grade(
		self,
		request,
		uuid=None,
	):
		submission = self.get_object()

		if submission.graded_at is not None:
			return Response(
				{"detail": "Bu topshiriq allaqachon baholangan."},
				status=(status.HTTP_400_BAD_REQUEST),
			)

		serializer = GradeSubmissionSerializer(data=request.data)

		serializer.is_valid(raise_exception=True)

		submission.grade = serializer.validated_data["grade"]

		submission.feedback = serializer.validated_data.get(
			"feedback",
			"",
		)

		submission.graded_at = timezone.now()

		submission.graded_by = request.user

		submission.save(
			update_fields=[
				"grade",
				"feedback",
				"graded_at",
				"graded_by",
			]
		)

		return Response(
			SubmissionSerializer(
				submission,
				context={"request": request},
			).data
		)


class StudentAssignmentViewSet(viewsets.ReadOnlyModelViewSet):
	serializer_class = StudentAssignmentSerializer
	permission_classes = (IsStudent,)
	lookup_field = "uuid"

	def get_queryset(self):
		user = self.request.user

		if not user.group_id:
			return Assignment.objects.none()

		my_submissions = Submission.objects.filter(student=user).order_by(
			"-submitted_at"
		)

		return (
			Assignment.objects.filter(groups=user.group)
			.select_related("teacher")
			.prefetch_related(
				Prefetch(
					"submissions",
					queryset=my_submissions,
					to_attr="student_submissions",
				)
			)
			.order_by("-created_at")
			.distinct()
		)


class StudentSubmissionViewSet(viewsets.ModelViewSet):
	serializer_class = StudentSubmissionSerializer
	permission_classes = (IsStudent,)
	lookup_field = "uuid"

	http_method_names = (
		"get",
		"post",
		"patch",
		"head",
		"options",
	)

	def get_queryset(self):
		return (
			Submission.objects.filter(student=self.request.user)
			.select_related("assignment")
			.order_by("-submitted_at")
		)

	def perform_update(
		self,
		serializer,
	):
		serializer.save(student=self.request.user)
