from datetime import time

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from shapely.geometry import Point, Polygon

from .models import (
	Attendance,
	AttendanceAttempt,
	AttendanceStep,
	Schedule,
)

ATTENDANCE_WINDOWS = {
	1: {
		1: {
			"start": time(8, 0),
			"end": time(10, 0),
		},
		2: {
			"start": time(10, 0),
			"end": time(12, 0),
		},
		3: {
			"start": time(12, 0),
			"end": time(13, 0),
		},
	},
	2: {
		1: {
			"start": time(13, 0),
			"end": time(14, 0),
		},
		2: {
			"start": time(14, 0),
			"end": time(16, 0),
		},
		3: {
			"start": time(16, 0),
			"end": time(18, 0),
		},
	},
}


WEEKDAY_FIELDS = {
	0: "monday",
	1: "tuesday",
	2: "wednesday",
	3: "thursday",
	4: "friday",
	5: "saturday",
}


def client_ip(request):
	xff = request.META.get("HTTP_X_FORWARDED_FOR")

	if xff:
		return xff.split(",")[0].strip()

	return request.META.get("REMOTE_ADDR")


def today_schedule(
	student,
	now=None,
):
	now = timezone.localtime(now or timezone.now())

	today = now.date()

	weekday_field = WEEKDAY_FIELDS.get(now.weekday())

	# Sunday
	if not weekday_field:
		return None

	filters = {
		"is_active": True,
		"location__is_active": True,
		"start_date__lte": today,
		"end_date__gte": today,
		weekday_field: True,
	}

	base_qs = Schedule.objects.filter(**filters).select_related(
		"user",
		"group",
		"location",
	)

	# Avval student uchun maxsus schedule
	personal_schedule = base_qs.filter(user=student).order_by("id").first()

	if personal_schedule:
		return personal_schedule

	# Keyin guruh schedule
	if not student.group_id:
		return None

	return base_qs.filter(group=student.group).order_by("id").first()


def shift_for_new_attendance(
	now=None,
):
	now = timezone.localtime(now or timezone.now())

	current_time = now.time().replace(tzinfo=None)

	if time(8, 0) <= current_time < time(13, 0):
		return 1

	if time(13, 0) <= current_time < time(18, 0):
		return 2

	return None


def display_shift(
	now=None,
):
	"""
	Attendance hali yaratilmaganida
	index page qaysi shiftni ko'rsatishi uchun.

	08:00 gacha -> 1-smena
	13:00 dan boshlab -> 2-smena
	"""
	now = timezone.localtime(now or timezone.now())

	current_time = now.time().replace(tzinfo=None)

	if current_time < time(13, 0):
		return 1

	return 2


def current_step_for_shift(
	shift,
	now=None,
):
	now = timezone.localtime(now or timezone.now())

	current_time = now.time().replace(tzinfo=None)

	steps = ATTENDANCE_WINDOWS.get(shift, {})

	for step, window in steps.items():
		if window["start"] <= current_time < window["end"]:
			return step

	return None


def point_in_location(
	latitude,
	longitude,
	location,
):
	try:
		latitude = float(latitude)

		longitude = float(longitude)

	except (
		TypeError,
		ValueError,
	):
		return False

	polygon = Polygon(location.polygon())

	student_point = Point(
		longitude,
		latitude,
	)

	return polygon.covers(student_point)


class FaceVerificationService:
	@staticmethod
	def verify(
		reference_path,
		probe_path,
	):
		try:
			from deepface import DeepFace

			cfg = settings.FACE_VERIFY

			anti_spoofing = cfg.get(
				"ANTI_SPOOFING",
				True,
			)

			liveness_verified = True

			# Faqat browserdan kelgan probe
			# rasmga anti-spoofing ishlatamiz.
			if anti_spoofing:
				faces = DeepFace.extract_faces(
					img_path=probe_path,
					detector_backend=(cfg["DETECTOR_BACKEND"]),
					enforce_detection=True,
					align=True,
					anti_spoofing=True,
				)

				if len(faces) != 1:
					return {
						"verified": False,
						"liveness_verified": False,
						"distance": None,
						"threshold": None,
						"error": ("Kadrda aynan bitta yuz bo'lishi kerak."),
					}

				liveness_verified = bool(
					faces[0].get(
						"is_real",
						False,
					)
				)

				if not liveness_verified:
					return {
						"verified": False,
						"liveness_verified": False,
						"distance": None,
						"threshold": None,
						"error": ("Jonli yuz tasdiqlanmadi."),
					}

			result = DeepFace.verify(
				img1_path=reference_path,
				img2_path=probe_path,
				model_name=(cfg["MODEL_NAME"]),
				detector_backend=(cfg["DETECTOR_BACKEND"]),
				distance_metric=(cfg["DISTANCE_METRIC"]),
				enforce_detection=True,
				align=True,
				anti_spoofing=False,
				silent=True,
			)

			return {
				"verified": bool(
					result.get(
						"verified",
						False,
					)
				),
				"liveness_verified": (liveness_verified),
				"distance": (result.get("distance")),
				"threshold": (result.get("threshold")),
				"error": None,
			}

		except Exception as exc:
			return {
				"verified": False,
				"liveness_verified": False,
				"distance": None,
				"threshold": None,
				"error": str(exc),
			}


def verify_attendance(
	request,
	student,
	image,
	latitude,
	longitude,
):
	now = timezone.localtime()

	today = now.date()

	if student.role != "student":
		raise ValidationError(
			{
				"code": "NOT_STUDENT",
				"detail": ("Faqat student davomat qiladi."),
			}
		)

	# -------------------------
	# SCHEDULE
	# -------------------------

	schedule = today_schedule(
		student=student,
		now=now,
	)

	if not schedule:
		raise ValidationError(
			{
				"code": "NO_SCHEDULE",
				"detail": ("Bugun siz uchun aktiv amaliyot mavjud emas."),
			}
		)

	# -------------------------
	# EXISTING ATTENDANCE
	# -------------------------

	attendance = Attendance.objects.filter(
		student=student,
		schedule=schedule,
		date=today,
	).first()

	# Attendance mavjud bo'lsa
	# shift hech qachon o'zgarmaydi.
	if attendance:
		shift = attendance.shift

	else:
		shift = shift_for_new_attendance(now)

		if shift is None:
			raise ValidationError(
				{
					"code": "STEP_CLOSED",
					"detail": ("Hozir davomat uchun ochiq vaqt mavjud emas."),
				}
			)

	# -------------------------
	# CURRENT STEP
	# -------------------------

	step_number = current_step_for_shift(
		shift=shift,
		now=now,
	)

	if step_number is None:
		raise ValidationError(
			{
				"code": "STEP_CLOSED",
				"detail": ("Hozir ushbu smena uchun ochiq qadam yo'q."),
			}
		)

	# -------------------------
	# CREATE / LOCK ATTENDANCE
	# -------------------------

	if not attendance:
		with transaction.atomic():
			attendance, _ = Attendance.objects.get_or_create(
				student=student,
				schedule=schedule,
				date=today,
				defaults={
					"shift": shift,
				},
			)

		# Race holatda boshqa request
		# attendance yaratib ulgurgan bo'lsa,
		# DB dagi shift authoritative.
		shift = attendance.shift

		step_number = current_step_for_shift(
			shift=shift,
			now=now,
		)

		if step_number is None:
			raise ValidationError(
				{
					"code": "STEP_CLOSED",
					"detail": ("Sizning davomat smenangiz uchun vaqt tugagan."),
				}
			)

	# -------------------------
	# ATTENDANCE STEP
	# -------------------------

	attendance_step, _ = AttendanceStep.objects.get_or_create(
		attendance=attendance,
		step=step_number,
		defaults={
			"success": False,
		},
	)

	# -------------------------
	# ATTEMPT AUDIT
	# -------------------------

	ip = client_ip(request)

	user_agent = request.META.get(
		"HTTP_USER_AGENT",
		"",
	)[:2000]

	attempt = AttendanceAttempt.objects.create(
		step=attendance_step,
		image=image,
		ip_address=ip,
		latitude=latitude,
		longitude=longitude,
		location=schedule.location,
		user_agent=user_agent,
	)

	def fail(
		code,
		message,
	):
		attempt.error_code = code
		attempt.error_message = message

		attempt.save(
			update_fields=[
				"error_code",
				"error_message",
			]
		)

		raise ValidationError(
			{
				"code": code,
				"detail": message,
			}
		)

	# -------------------------
	# ALREADY DONE
	# -------------------------

	if attendance_step.success:
		fail(
			"ALREADY_VERIFIED",
			"Bu qadam avval tasdiqlangan.",
		)

	# -------------------------
	# LOCATION
	# -------------------------

	if not point_in_location(
		latitude=latitude,
		longitude=longitude,
		location=schedule.location,
	):
		fail(
			"OUTSIDE_LOCATION",
			("Siz belgilangan amaliyot hududida emassiz."),
		)

	attempt.location_verified = True

	attempt.save(
		update_fields=[
			"location_verified",
		]
	)

	# -------------------------
	# REFERENCE FACE
	# -------------------------

	if not student.image:
		fail(
			"NO_REFERENCE_FACE",
			("HEMIS profil rasmi topilmadi."),
		)

	try:
		reference_path = student.image.path

		probe_path = attempt.image.path

	except Exception:
		fail(
			"IMAGE_ERROR",
			"Yuz rasmini ochib bo'lmadi.",
		)

	# -------------------------
	# FACE
	# -------------------------

	result = FaceVerificationService.verify(
		reference_path=reference_path,
		probe_path=probe_path,
	)

	attempt.face_verified = result.get(
		"verified",
		False,
	)

	attempt.liveness_verified = result.get(
		"liveness_verified",
		False,
	)

	attempt.face_distance = result.get("distance")

	attempt.face_threshold = result.get("threshold")

	attempt.save(
		update_fields=[
			"face_verified",
			"liveness_verified",
			"face_distance",
			"face_threshold",
		]
	)

	if not result.get(
		"liveness_verified",
		False,
	):
		fail(
			"LIVENESS_FAILED",
			result.get("error") or ("Jonli yuz tasdiqlanmadi."),
		)

	if not result.get(
		"verified",
		False,
	):
		fail(
			"FACE_MISMATCH",
			result.get("error") or ("Yuz HEMIS profil rasmiga mos kelmadi."),
		)

	# -------------------------
	# SUCCESS
	# -------------------------

	with transaction.atomic():
		locked_step = AttendanceStep.objects.select_for_update().get(
			pk=attendance_step.pk
		)

		if locked_step.success:
			attempt.error_code = "ALREADY_VERIFIED"

			attempt.error_message = "Bu qadam avval tasdiqlangan."

			attempt.save(
				update_fields=[
					"error_code",
					"error_message",
				]
			)

			raise ValidationError(
				{
					"code": "ALREADY_VERIFIED",
					"detail": "Bu qadam avval tasdiqlangan.",
				}
			)

		locked_step.success = True

		locked_step.save(
			update_fields=[
				"success",
			]
		)

		attempt.success = True

		attempt.save(
			update_fields=[
				"success",
			]
		)

	return {
		"attendance": attendance,
		"step": locked_step,
		"attempt": attempt,
	}
