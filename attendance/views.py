from datetime import date, timedelta

from django.db.models import Count, Prefetch, Q
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import decorators, generics, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from attendance.hemis import sync_hemis_groups
from users.models import User
from users.permissions import (
	Can,
	IsStaffRole,
	IsStudent,
	ModelPermission,
	user_can,
	visible_groups,
)

from .models import Attendance, AttendanceAttempt, AttendanceStep, Location, Schedule
from .serializers import (
	AttemptListSerializer,
	AttemptSerializer,
	AttendanceDetailSerializer,
	AttendanceSerializer,
	AttendanceSummarySerializer,
	CheckInSerializer,
	DayStateSerializer,
	LocationCheckSerializer,
	LocationSerializer,
	ScheduleSerializer,
	StudentAttemptSerializer,
)
from .services import (
	ERROR_MESSAGES,
	LOCATION_TOKEN_MAX_AGE,
	CheckInError,
	check_in,
	day_state,
	day_steps,
	is_schedule_day,
	passed_steps,
	practice_students_by_day,
	schedule_for,
	verify_location,
)


def client_ip(request):
	forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
	if forwarded:
		return forwarded.split(",")[0].strip()
	return request.META.get("REMOTE_ADDR")


def parse_date(value, default: date | None = None) -> date | None:
	if not value:
		return default
	try:
		return date.fromisoformat(value)
	except ValueError as e:
		raise ValidationError({"date": "Sana formati: YYYY-MM-DD"}) from e


def attendance_queryset():
	return Attendance.objects.select_related("schedule__location").prefetch_related(
		Prefetch(
			"steps",
			queryset=AttendanceStep.objects.order_by("step").prefetch_related(
				Prefetch(
					"attempts",
					queryset=AttendanceAttempt.objects.order_by("attempted_at"),
				)
			),
		)
	)


# --- talaba ---


class TodayView(APIView):
	"""Bugungi holat: jadval, smena, qadamlar va hozir tasdiqlash mumkinmi."""

	permission_classes = (IsStudent,)

	def get(self, request):
		return Response(
			DayStateSerializer(
				day_state(request.user), context={"request": request}
			).data
		)


class LocationCheckView(APIView):
	"""
	Joylashuvni oldindan tekshirish: latitude, longitude, accuracy.
	ok=true bo'lsa check-in uchun 5 daqiqalik `token` qaytadi - usiz kamera (FaceID) bosqichiga o'tib bo'lmaydi.
	"""

	permission_classes = (IsStudent,)

	def post(self, request):
		serializer = LocationCheckSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		schedule = schedule_for(request.user, timezone.localdate())
		if not schedule:
			return Response(
				{"detail": "Bugun amaliyot kuni emas"},
				status=status.HTTP_400_BAD_REQUEST,
			)

		result = verify_location(
			request.user, schedule.location, **serializer.validated_data
		)
		return Response(
			{
				"ok": result.ok,
				"error_code": result.error_code,
				"message": result.message,
				"distance": result.distance,
				"location": {
					"uuid": schedule.location.uuid,
					"name": schedule.location.name,
				},
				"token": result.token or None,
				"expires_in": LOCATION_TOKEN_MAX_AGE if result.ok else None,
			}
		)


class CheckInView(APIView):
	"""multipart: latitude, longitude, accuracy, location_token, image"""

	permission_classes = (IsStudent,)

	def post(self, request):
		serializer = CheckInSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		try:
			attempt = check_in(
				request.user,
				**serializer.validated_data,
				user_agent=request.META.get("HTTP_USER_AGENT", ""),
				ip_address=client_ip(request),
			)
		except CheckInError as e:
			return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

		context = {"request": request}
		return Response(
			{
				"attempt": StudentAttemptSerializer(attempt).data,
				"state": DayStateSerializer(
					day_state(request.user), context=context
				).data,
			},
			status=status.HTTP_201_CREATED,
		)


class MySchedulesView(APIView):
	permission_classes = (IsStudent,)

	def get(self, request):
		user = request.user
		group_q = Q(group_id=user.group_id) if user.group_id else Q(pk__in=[])
		schedules = (
			Schedule.objects.filter(
				Q(user=user) | group_q,
				is_active=True,
				end_date__gte=timezone.localdate(),
			)
			.select_related("location", "group", "user")
			.order_by("start_date")
		)
		return Response(
			ScheduleSerializer(schedules, many=True, context={"request": request}).data
		)


# --- o'qituvchi / dekan / admin ---


@decorators.api_view(http_method_names=["POST"])
def sync_groups(request: HttpRequest):
	sync_hemis_groups()
	return Response({"status": "ok"})


class GroupListView(APIView):
	permission_classes = (Can("users.view_group"),)

	def get(self, request):
		groups = visible_groups(request.user).annotate(
			students_count=Count("students", filter=Q(students__role="student"))
		)
		if search := request.query_params.get("search"):
			groups = groups.filter(name__icontains=search)
		today = timezone.localdate()
		groups = groups.prefetch_related(
			Prefetch(
				"schedules",
				queryset=Schedule.objects.filter(
					is_active=True, end_date__gte=today
				).select_related("location"),
				to_attr="active_schedules",
			)
		)
		return Response(
			[
				{
					"uuid": g.uuid,
					"name": g.name,
					"faculty": g.faculty.name if g.faculty else None,
					"teacher": g.teacher.full_name if g.teacher else None,
					"teacher_uuid": g.teacher.uuid if g.teacher else None,
					"students_count": g.students_count,
					"schedules": ScheduleSerializer(g.active_schedules, many=True).data,
				}
				for g in groups
			]
		)


def _student_row(request, student, attendance, steps=None):
	return {
		"uuid": student.uuid,
		"full_name": student.full_name or student.username,
		"username": student.username,
		"image": request.build_absolute_uri(student.image.url)
		if student.image
		else None,
		"is_active": student.is_active,
		"attendance_uuid": attendance.uuid if attendance else None,
		# smena faqat muvaffaqiyatli qadamdan keyin qulflanadi - unga qadar ko'rsatilmaydi
		"shift": attendance.shift if attendance and passed_steps(attendance) else None,
		"passed_steps": sorted(s.step for s in attendance.steps.all() if s.success)
		if attendance
		else [],
		# har bir qadam holati: passed | missed | available | upcoming; amaliyot kuni bo'lmasa - null
		"steps": steps,
	}


class GroupAttendanceView(APIView):
	"""Guruhning bitta kundagi davomati: ?date=YYYY-MM-DD"""

	permission_classes = (Can("attendance.view_attendance"),)

	def get(self, request, uuid):
		group = get_object_or_404(visible_groups(request.user), uuid=uuid)
		day = parse_date(request.query_params.get("date"), timezone.localdate())

		students = (
			User.objects.filter(group=group, role="student")
			.order_by("full_name")
			.prefetch_related(
				Prefetch(
					"attendances",
					queryset=Attendance.objects.filter(date=day).prefetch_related(
						"steps"
					),
					to_attr="day_attendances",
				)
			)
		)
		rows = []
		practice_students = 0
		now = timezone.now()
		for student in students:
			attendance = student.day_attendances[0] if student.day_attendances else None
			steps = None
			if schedule_for(student, day):
				practice_students += 1
				passed = passed_steps(attendance)
				_, states = day_steps(
					passed, attendance.shift if passed else None, day, now
				)
				steps = [st.status for st in states]
			rows.append(_student_row(request, student, attendance, steps))

		return Response(
			{
				"group": {
					"uuid": group.uuid,
					"name": group.name,
					"teacher": {
						"uuid": group.teacher.uuid,
						"full_name": group.teacher.full_name,
					}
					if group.teacher
					else None,
				},
				"date": day,
				"is_practice_day": practice_students > 0,
				"students": rows,
			}
		)


class GroupReportView(APIView):
	"""Davr hisoboti: ?from=YYYY-MM-DD&to=YYYY-MM-DD. Har bir amaliyot kuni uchun o'tilgan qadamlar soni."""

	permission_classes = (Can("attendance.view_attendance"),)

	def get(self, request, uuid):
		group = get_object_or_404(visible_groups(request.user), uuid=uuid)
		date_to = parse_date(request.query_params.get("to"), timezone.localdate())
		date_from = parse_date(
			request.query_params.get("from"), date_to - timedelta(days=30)
		)
		if date_from > date_to or (date_to - date_from).days > 120:
			raise ValidationError({"detail": "Davr noto'g'ri yoki 120 kundan oshadi"})

		students = list(
			User.objects.filter(group=group, role="student").order_by("full_name")
		)
		schedules = list(
			Schedule.objects.filter(
				Q(group=group) | Q(user__in=students),
				is_active=True,
				start_date__lte=date_to,
				end_date__gte=date_from,
			)
		)

		days = []
		day = date_from
		while day <= date_to:
			if any(is_schedule_day(s, day) for s in schedules):
				days.append(day)
			day += timedelta(days=1)

		attendances = Attendance.objects.filter(
			student__in=students, date__in=days
		).prefetch_related("steps")
		by_student = {}
		for a in attendances:
			by_student.setdefault(a.student_id, {})[a.date.isoformat()] = {
				"shift": a.shift,
				"passed": sum(1 for s in a.steps.all() if s.success),
			}

		return Response(
			{
				"group": {"uuid": group.uuid, "name": group.name},
				"from": date_from,
				"to": date_to,
				"days": days,
				"students": [
					{
						"uuid": s.uuid,
						"full_name": s.full_name or s.username,
						"days": by_student.get(s.id, {}),
					}
					for s in students
				],
			}
		)


class StudentAttendancesView(APIView):
	"""
	Bitta talabaning davomatlari. ?date= ixtiyoriy.
	Urinishlar (rasm, lokatsiya, faceid natijalari) faqat attendance.view_attendanceattempt bilan.
	"""

	permission_classes = (Can("attendance.view_attendance"),)

	def get(self, request, uuid):
		student = get_object_or_404(
			User.objects.filter(role="student", group__in=visible_groups(request.user)),
			uuid=uuid,
		)
		can_attempts = user_can(request.user, "attendance.view_attendanceattempt")
		serializer = (
			AttendanceDetailSerializer if can_attempts else AttendanceSummarySerializer
		)
		attendances = (
			attendance_queryset()
			if can_attempts
			else Attendance.objects.select_related(
				"schedule__location"
			).prefetch_related("steps")
		)
		attendances = attendances.filter(student=student).order_by("-date")
		if day := parse_date(request.query_params.get("date")):
			attendances = attendances.filter(date=day)
		return Response(
			{
				"student": {
					"uuid": student.uuid,
					"full_name": student.full_name or student.username,
					"username": student.username,
					"group": student.group.name if student.group else None,
					"image": request.build_absolute_uri(student.image.url)
					if student.image
					else None,
					"is_active": student.is_active,
				},
				# urinishlar (rasm, GPS, yuz masofasi) - faqat ruxsat bo'lsa; aks holda faqat qadamlar holati
				"can_view_attempts": can_attempts,
				"attendances": serializer(
					attendances[:60], many=True, context={"request": request}
				).data,
			}
		)


class AttemptPagination(PageNumberPagination):
	page_size = 20
	page_size_query_param = "page_size"
	max_page_size = 100


class AttemptListView(generics.ListAPIView):
	"""
	Barcha urinishlar (rolga qarab ko'rinadigan guruhlar bo'yicha).
	Filtrlar: from, to (YYYY-MM-DD), group (uuid), search (F.I.Sh / login), result (success|fail),
	error_code, step (1-3), shift (1-2), location (uuid). Pagination: page, page_size.
	"""

	permission_classes = (Can("attendance.view_attendanceattempt"),)
	serializer_class = AttemptListSerializer
	pagination_class = AttemptPagination

	def get_queryset(self):
		params = self.request.query_params
		qs = AttendanceAttempt.objects.filter(
			step__attendance__student__group__in=visible_groups(self.request.user)
		).select_related(
			"step__attendance__student__group",
			"step__attendance__schedule",
			"location",
		)
		if date_from := parse_date(params.get("from")):
			qs = qs.filter(attempted_at__date__gte=date_from)
		if date_to := parse_date(params.get("to")):
			qs = qs.filter(attempted_at__date__lte=date_to)
		if group := params.get("group"):
			qs = qs.filter(step__attendance__student__group__uuid=group)
		if location := params.get("location"):
			qs = qs.filter(location__uuid=location)
		if search := params.get("search", "").strip():
			qs = qs.filter(
				Q(step__attendance__student__full_name__icontains=search)
				| Q(step__attendance__student__username__icontains=search)
			)
		if params.get("result") == "success":
			qs = qs.filter(success=True)
		elif params.get("result") == "fail":
			qs = qs.filter(success=False)
		if error_code := params.get("error_code"):
			qs = qs.filter(error_code=error_code)
		if (step := params.get("step")) in ("1", "2", "3"):
			qs = qs.filter(step__step=step)
		if (shift := params.get("shift")) in ("1", "2"):
			qs = qs.filter(step__attendance__shift=shift)
		return qs.order_by("-attempted_at")


class AttemptFiltersView(APIView):
	"""Urinishlar sahifasidagi filtrlar uchun variantlar."""

	permission_classes = (Can("attendance.view_attendanceattempt"),)

	def get(self, request):
		return Response(
			{
				"error_codes": [
					{"code": code, "label": label}
					for code, label in ERROR_MESSAGES.items()
				],
			}
		)


class DashboardView(APIView):
	"""
	Bosh sahifa statistikasi - faqat ko'rinadigan guruhlar bo'yicha
	(o'qituvchi - o'ziga biriktirilgan guruhlar, dekan - fakulteti, admin/little - hammasi).
	"""

	permission_classes = (IsStaffRole,)
	TREND_DAYS = 14

	@staticmethod
	def assignments_stats(user, groups):
		if not user_can(user, "assignments.view_assignment"):
			return None
		from assignments.models import Assignment, Submission

		assignments = Assignment.objects.filter(groups__in=groups)
		if user.role == "teacher":
			assignments = Assignment.objects.filter(teacher=user)
		assignments = assignments.distinct()
		now = timezone.now()
		submissions = Submission.objects.filter(assignment__in=assignments)
		return {
			"active": assignments.filter(deadline__gte=now).count(),
			"submitted": submissions.count(),
			"ungraded": submissions.filter(graded_at__isnull=True).count(),
		}

	def get(self, request):
		today = timezone.localdate()
		groups = visible_groups(request.user)
		students = list(
			User.objects.filter(role="student", group__in=groups).values_list(
				"id", "group_id"
			)
		)
		student_ids = {sid for sid, _ in students}
		days = [today - timedelta(days=i) for i in range(self.TREND_DAYS - 1, -1, -1)]
		schedules = list(
			Schedule.objects.filter(
				Q(group__in=groups) | Q(user_id__in=student_ids),
				is_active=True,
				start_date__lte=today,
				end_date__gte=days[0],
			)
		)
		expected = practice_students_by_day(students, schedules, days)

		# kunlar bo'yicha kamida bitta qadam tasdiqlagan / 3 ta qadamni ham tasdiqlagan talabalar
		passed_counts = (
			AttendanceStep.objects.filter(
				success=True,
				attendance__student_id__in=student_ids,
				attendance__date__gte=days[0],
				attendance__date__lte=today,
			)
			.values("attendance__student_id", "attendance__date")
			.annotate(n=Count("id"))
		)
		came: dict = {d: set() for d in days}
		full: dict = {d: set() for d in days}
		for row in passed_counts:
			came[row["attendance__date"]].add(row["attendance__student_id"])
			if row["n"] >= 3:
				full[row["attendance__date"]].add(row["attendance__student_id"])

		# bugungi urinishlar
		can_attempts = user_can(request.user, "attendance.view_attendanceattempt")
		attempts_today = AttendanceAttempt.objects.filter(
			step__attendance__student_id__in=student_ids, attempted_at__date=today
		)
		by_error = dict(
			attempts_today.filter(success=False)
			.values_list("error_code")
			.annotate(n=Count("id"))
			.values_list("error_code", "n")
		)
		success_today = attempts_today.filter(success=True).count()
		failed_today = sum(by_error.values())

		# guruhlar kesimida bugun
		group_names = dict(groups.values_list("id", "name"))
		group_uuids = dict(groups.values_list("id", "uuid"))
		student_group = dict(students)
		group_rows: dict[int, dict] = {}
		for sid in expected[today]:
			gid = student_group.get(sid)
			row = group_rows.setdefault(
				gid,
				{
					"uuid": group_uuids.get(gid),
					"name": group_names.get(gid, "—"),
					"expected": 0,
					"came": 0,
					"full": 0,
				},
			)
			row["expected"] += 1
			row["came"] += sid in came[today]
			row["full"] += sid in full[today]

		recent_failures = (
			AttendanceAttempt.objects.filter(
				step__attendance__student_id__in=student_ids, success=False
			)
			.select_related("step__attendance__student__group", "location")
			.order_by("-attempted_at")[:8]
		)

		return Response(
			{
				"date": today,
				"totals": {
					"students": len(student_ids),
					"groups": len(group_names),
					"locations": len(
						{s.location_id for s in schedules if s.end_date >= today}
					),
					"schedules": sum(1 for s in schedules if s.end_date >= today),
				},
				"today": {
					"expected": len(expected[today]),
					"came": len(came[today] & expected[today]),
					"full": len(full[today] & expected[today]),
				},
				# urinishlar statistikasi - faqat urinishlarni ko'rish ruxsati bo'lsa (admin / little)
				"attempts_today": {
					"total": success_today + failed_today,
					"success": success_today,
					"failed": failed_today,
					"by_error": [
						{
							"code": code,
							"label": ERROR_MESSAGES.get(code, code),
							"count": n,
						}
						for code, n in sorted(by_error.items(), key=lambda x: -x[1])
					],
				}
				if can_attempts
				else None,
				"assignments": self.assignments_stats(request.user, groups),
				"trend": [
					{
						"date": d,
						"expected": len(expected[d]),
						"came": len(came[d] & expected[d]),
						"full": len(full[d] & expected[d]),
					}
					for d in days
				],
				"groups": sorted(
					group_rows.values(), key=lambda r: (-r["expected"], r["name"])
				),
				# rasmli urinishlar - faqat urinishlarni ko'rish ruxsati bo'lsa
				"recent_failures": AttemptListSerializer(
					recent_failures, many=True, context={"request": request}
				).data
				if can_attempts
				else [],
			}
		)


# --- admin: lokatsiya va jadval ---


class LocationViewSet(viewsets.ModelViewSet):
	permission_classes = (ModelPermission("attendance.location"),)
	serializer_class = LocationSerializer
	lookup_field = "uuid"
	pagination_class = None

	def get_queryset(self):
		qs = Location.objects.order_by("name")
		if search := self.request.query_params.get("search"):
			qs = qs.filter(name__icontains=search)
		return qs

	def destroy(self, request, *args, **kwargs):
		location = self.get_object()
		if location.schedules.exists() or location.attempts.exists():
			return Response(
				{"detail": "Lokatsiya ishlatilgan. O'chirish o'rniga nofaol qiling"},
				status=status.HTTP_400_BAD_REQUEST,
			)
		return super().destroy(request, *args, **kwargs)


class ScheduleViewSet(viewsets.ModelViewSet):
	permission_classes = (ModelPermission("attendance.schedule"),)
	serializer_class = ScheduleSerializer
	lookup_field = "uuid"
	pagination_class = None

	def get_queryset(self):
		groups = visible_groups(self.request.user)
		qs = (
			Schedule.objects.filter(Q(group__in=groups) | Q(user__group__in=groups))
			.select_related("location", "group", "user")
			.order_by("-start_date")
		)
		params = self.request.query_params
		if group := params.get("group"):
			qs = qs.filter(Q(group__uuid=group) | Q(user__group__uuid=group))
		if location := params.get("location"):
			qs = qs.filter(location__uuid=location)
		if params.get("active") == "1":
			qs = qs.filter(is_active=True, end_date__gte=timezone.localdate())
		return qs

	def destroy(self, request, *args, **kwargs):
		schedule = self.get_object()
		if schedule.attendances.exists():
			return Response(
				{
					"detail": "Jadval bo'yicha davomat bor. O'chirish o'rniga nofaol qiling"
				},
				status=status.HTTP_400_BAD_REQUEST,
			)
		return super().destroy(request, *args, **kwargs)
