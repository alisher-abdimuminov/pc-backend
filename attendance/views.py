from datetime import date, timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import (
	api_view,
	permission_classes,
)
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from users.models import Group, User
from users.permissions import IsAdmin, IsStudent, IsTeacher

from .models import Attendance, AttendanceAttempt, AttendanceStep, Location, Schedule
from .serializers import (
	AttendanceAttemptSerializer,
	AttendanceCheckSerializer,
	AttendanceMonitoringSerializer,
	LocationSerializer,
	ScheduleSerializer,
)
from .services import (
	ATTENDANCE_WINDOWS,
	current_step_for_shift,
	display_shift,
	today_schedule,
	verify_attendance,
)


class LocationViewSet(viewsets.ModelViewSet):
	lookup_field = "uuid"
	queryset = Location.objects.all().order_by("name")
	serializer_class = LocationSerializer
	permission_classes = (IsAdmin,)


class ScheduleViewSet(viewsets.ModelViewSet):
	lookup_field = "uuid"
	queryset = Schedule.objects.all().order_by("name")
	serializer_class = ScheduleSerializer
	permission_classes = (IsAdmin,)


class AttendanceMonitoringViewSet(viewsets.ViewSet):
	permission_classes = (IsTeacher | IsAdmin,)

	def list(self, request):
		group_uuid = request.query_params.get("group")

		if not group_uuid:
			return Response(
				{"detail": ("group parametri majburiy.")},
				status=status.HTTP_400_BAD_REQUEST,
			)

		# ----------------------------------
		# GROUP
		# ----------------------------------

		group_queryset = Group.objects.all()

		if request.user.role == "teacher":
			group_queryset = group_queryset.filter(teacher=request.user)

		group = get_object_or_404(
			group_queryset,
			uuid=group_uuid,
		)

		# ----------------------------------
		# DATE RANGE
		# ----------------------------------

		start_date_param = request.query_params.get("start_date")

		end_date_param = request.query_params.get("end_date")

		if start_date_param or end_date_param:
			if not start_date_param or not end_date_param:
				return Response(
					{"detail": ("start_date va end_date birga yuborilishi kerak.")},
					status=(status.HTTP_400_BAD_REQUEST),
				)

			try:
				start_date = date.fromisoformat(start_date_param)

				end_date = date.fromisoformat(end_date_param)

			except ValueError:
				return Response(
					{"detail": ("Sana formati YYYY-MM-DD bo'lishi kerak.")},
					status=(status.HTTP_400_BAD_REQUEST),
				)

			if start_date > end_date:
				return Response(
					{"detail": ("start_date end_date'dan katta bo'lishi mumkin emas.")},
					status=(status.HTTP_400_BAD_REQUEST),
				)

		else:
			# Default:
			# joriy hafta
			# Dushanba - Yakshanba

			today = timezone.localdate()

			start_date = today - timedelta(days=today.weekday())

			end_date = start_date + timedelta(days=6)

		# ----------------------------------
		# DATES
		# ----------------------------------

		dates = []

		current_date = start_date

		while current_date <= end_date:
			dates.append(current_date)

			current_date += timedelta(days=1)

		# ----------------------------------
		# STUDENTS
		# ----------------------------------

		students = list(
			User.objects.filter(
				role="student",
				group=group,
			)
			.only(
				"id",
				"uuid",
				"full_name",
			)
			.order_by("full_name")
		)

		# ----------------------------------
		# SUCCESSFUL STEPS
		# ----------------------------------

		step_rows = AttendanceStep.objects.filter(
			attendance__student__in=students,
			attendance__date__range=(
				start_date,
				end_date,
			),
			success=True,
		).values(
			"attendance__student_id",
			"attendance__date",
			"step",
		)

		# {
		#     (student_id, date):
		#         [True, False, True]
		# }

		status_map = {}

		for row in step_rows:
			key = (
				row["attendance__student_id"],
				row["attendance__date"],
			)

			if key not in status_map:
				status_map[key] = [
					False,
					False,
					False,
				]

			step = row["step"]

			if step in [1, 2, 3]:
				status_map[key][step - 1] = True

		# ----------------------------------
		# RESPONSE STUDENTS
		# ----------------------------------

		result_students = []

		for student in students:
			student_days = []

			for current_date in dates:
				steps = status_map.get(
					(
						student.id,
						current_date,
					),
					[
						False,
						False,
						False,
					],
				)

				student_days.append(
					{
						"date": current_date,
						"step_1": steps[0],
						"step_2": steps[1],
						"step_3": steps[2],
					}
				)

			result_students.append(
				{
					"uuid": student.uuid,
					"full_name": student.full_name,
					"days": student_days,
				}
			)

		# ----------------------------------
		# RESPONSE
		# ----------------------------------

		data = {
			"group_uuid": group.uuid,
			"group_name": group.name,
			"start_date": start_date,
			"end_date": end_date,
			"dates": dates,
			"students": result_students,
		}

		serializer = AttendanceMonitoringSerializer(data)

		return Response(serializer.data)


class AttendanceAttemptViewSet(viewsets.ReadOnlyModelViewSet):
	serializer_class = AttendanceAttemptSerializer
	permission_classes = (IsAdmin,)

	filter_backends = (SearchFilter,)

	search_fields = (
		"step__attendance__student__full_name",
		"step__attendance__student__username",
		"location__name",
		"error_code",
		"error_message",
		"ip_address",
	)

	def get_queryset(self):
		qs = AttendanceAttempt.objects.select_related(
			"step",
			"step__attendance",
			"step__attendance__student",
			"step__attendance__schedule",
			"location",
		).order_by("-attempted_at")

		date = self.request.query_params.get("date")

		status_value = self.request.query_params.get("status")

		step = self.request.query_params.get("step")

		if date:
			qs = qs.filter(attempted_at__date=date)

		if status_value == "success":
			qs = qs.filter(success=True)

		elif status_value == "failed":
			qs = qs.filter(success=False)

		if step in ["1", "2", "3"]:
			qs = qs.filter(step__step=step)

		return qs


def format_time(value):
	return value.strftime("%H:%M")


@api_view(["GET"])
@permission_classes([IsStudent])
def today(request):
	now = timezone.localtime()

	today_date = now.date()

	schedule = today_schedule(
		student=request.user,
		now=now,
	)

	if not schedule:
		return Response(
			{
				"has_schedule": False,
				"date": today_date,
				"server_time": now,
				"steps": [],
			}
		)

	attendance = (
		Attendance.objects.filter(
			student=request.user,
			schedule=schedule,
			date=today_date,
		)
		.prefetch_related("steps")
		.first()
	)

	# Attendance yaratilgan bo'lsa
	# uning shift'i qat'iy.
	if attendance:
		shift = attendance.shift

	else:
		shift = display_shift(now)

	current_step = current_step_for_shift(
		shift=shift,
		now=now,
	)

	completed = set()

	if attendance:
		completed = {item.step for item in attendance.steps.all() if item.success}

	current_time = now.time().replace(tzinfo=None)

	steps = []

	for (
		step_number,
		window,
	) in ATTENDANCE_WINDOWS[shift].items():
		if step_number in completed:
			step_status = "completed"

		elif current_step == step_number:
			step_status = "available"

		elif current_time >= window["end"]:
			step_status = "missed"

		else:
			step_status = "locked"

		steps.append(
			{
				"step": step_number,
				"start": format_time(window["start"]),
				"end": format_time(window["end"]),
				"status": step_status,
			}
		)

	return Response(
		{
			"has_schedule": True,
			"date": today_date,
			"server_time": now,
			"schedule_uuid": schedule.uuid,
			"schedule_name": schedule.name,
			"shift": shift,
			"shift_name": f"{shift}-SMENA",
			"attendance_uuid": (attendance.uuid if attendance else None),
			"location": {
				"uuid": schedule.location.uuid,
				"name": schedule.location.name,
			},
			"steps": steps,
		}
	)


@api_view(["POST"])
@permission_classes([IsStudent])
def check(request):
	serializer = AttendanceCheckSerializer(data=request.data)

	serializer.is_valid(raise_exception=True)

	data = serializer.validated_data

	result = verify_attendance(
		request=request,
		student=request.user,
		image=data["face_image"],
		latitude=data["latitude"],
		longitude=data["longitude"],
	)

	return Response(
		{
			"success": True,
			"attendance_uuid": (result["attendance"].uuid),
			"shift": (result["attendance"].shift),
			"step": (result["step"].step),
			"message": ("Davomat muvaffaqiyatli tasdiqlandi."),
		},
		status=(status.HTTP_201_CREATED),
	)
