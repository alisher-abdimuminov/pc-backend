from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from users.models import User
from users.permissions import Can, IsStudent, IsTeacher, visible_groups

from .models import Assignment, Submission
from .serializers import AssignmentSerializer, GradeSerializer, SubmissionSerializer, SubmitSerializer


class AssignmentViewSet(viewsets.ModelViewSet):
	"""
	O'qituvchi: o'z topshiriqlarini yaratadi/tahrirlaydi, topshirilganlarni ko'radi.
	Talaba: o'z guruhiga berilgan topshiriqlarni ko'radi va fayl topshiradi.
	Dekan/admin: ko'rinadigan guruhlar topshiriqlarini ko'radi.
	"""

	serializer_class = AssignmentSerializer
	lookup_field = "uuid"

	def get_permissions(self):
		if self.action in ("create", "update", "partial_update", "destroy"):
			return [IsTeacher()]
		if self.action == "submit":
			return [IsStudent()]
		if self.action == "submissions" or self.request.user.role not in ("student", "teacher"):
			# dekan/admin/little - ruxsat bo'yicha
			return [Can("assignments.view_assignment")()]
		return super().get_permissions()

	def get_queryset(self):
		user = self.request.user
		qs = Assignment.objects.select_related("teacher").prefetch_related("groups").order_by("-deadline")
		if user.role == "student":
			qs = qs.filter(groups=user.group_id).prefetch_related(
				Prefetch(
					"submissions",
					queryset=Submission.objects.filter(student=user).select_related("student__group", "graded_by"),
					to_attr="my_submissions",
				)
			)
		elif user.role == "teacher":
			qs = qs.filter(teacher=user)
		else:
			qs = qs.filter(groups__in=visible_groups(user)).distinct()

		if user.role != "student":
			qs = qs.annotate(submissions_count=Count("submissions", distinct=True))
		if group := self.request.query_params.get("group"):
			qs = qs.filter(groups__uuid=group)
		if self.request.query_params.get("active") == "1":
			qs = qs.filter(deadline__gte=timezone.now())
		return qs

	def get_serializer_context(self):
		context = super().get_serializer_context()
		context["allowed_groups"] = visible_groups(self.request.user)
		return context

	def perform_create(self, serializer):
		serializer.save(teacher=self.request.user)

	@action(detail=True, methods=["post"])
	def submit(self, request, uuid=None):
		"""Talaba fayl topshiradi. Muddat tugaguncha va baholanmaguncha qayta topshirish mumkin."""
		assignment = self.get_object()
		if assignment.deadline < timezone.now():
			return Response({"detail": "Topshirish muddati tugagan"}, status=status.HTTP_400_BAD_REQUEST)

		serializer = SubmitSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)

		submission = Submission.objects.filter(assignment=assignment, student=request.user).first()
		if submission and submission.graded_at:
			return Response({"detail": "Topshiriq baholangan, qayta yuborib bo'lmaydi"}, status=status.HTTP_400_BAD_REQUEST)
		submission = submission or Submission(assignment=assignment, student=request.user)
		submission.file = serializer.validated_data["file"]
		submission.save()
		return Response(SubmissionSerializer(submission, context={"request": request}).data, status=status.HTTP_201_CREATED)

	@action(detail=True, methods=["get"])
	def submissions(self, request, uuid=None):
		"""Topshiriq bo'yicha barcha talabalar: topshirganlar va topshirmaganlar."""
		assignment = self.get_object()
		submissions = {
			s.student_id: s
			for s in assignment.submissions.select_related("student__group", "graded_by")
		}
		students = User.objects.filter(role="student", group__in=assignment.groups.all()).select_related("group").order_by(
			"group__name", "full_name"
		)
		context = {"request": request}
		return Response(
			[
				{
					"student": {
						"uuid": s.uuid,
						"full_name": s.full_name or s.username,
						"group": s.group.name if s.group else None,
					},
					"submission": SubmissionSerializer(submissions[s.id], context=context).data
					if s.id in submissions
					else None,
				}
				for s in students
			]
		)


class SubmissionViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
	serializer_class = SubmissionSerializer
	lookup_field = "uuid"
	permission_classes = (IsTeacher,)

	def get_queryset(self):
		return Submission.objects.filter(assignment__teacher=self.request.user).select_related(
			"student__group", "graded_by"
		)

	@action(detail=True, methods=["post"])
	def grade(self, request, uuid=None):
		submission = self.get_object()
		if submission.assignment.teacher_id != request.user.id:
			raise PermissionDenied
		serializer = GradeSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		submission.grade = serializer.validated_data["grade"]
		submission.feedback = serializer.validated_data["feedback"]
		submission.graded_at = timezone.now()
		submission.graded_by = request.user
		# submitted_at auto_now - baholashda o'zgarmasligi uchun update_fields
		submission.save(update_fields=["grade", "feedback", "graded_at", "graded_by"])
		return Response(SubmissionSerializer(submission, context={"request": request}).data)
