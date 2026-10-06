"""
Amaliyot davomati logikasi.

Smena jadvalda berilmaydi - talabaning attempti vaqtiga qarab belgilanadi:
	08:00-13:00 -> 1-smena, 13:00-18:00 -> 2-smena.
Bitta qadam muvaffaqiyatli tasdiqlangach smena qulflanadi va talaba faqat shu smena qadamlarida
tasdiqlay oladi. Qadamlar majburiy emas - hozir qaysi qadam ochiq bo'lsa, o'shanda tasdiqlanadi.
"""

import math
from dataclasses import dataclass, field
from datetime import date, datetime, time

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.db.models import Case, IntegerField, Q, Value, When
from django.utils import timezone
from shapely.geometry import MultiPoint, Point

from . import face
from .models import Attendance, AttendanceAttempt, AttendanceStep, Location, Schedule

SHIFT_WINDOWS = {
	1: (
		(1, time(8, 0), time(10, 0)),
		(2, time(10, 0), time(12, 0)),
		(3, time(12, 0), time(13, 0)),
	),
	2: (
		(1, time(13, 0), time(14, 0)),
		(2, time(14, 0), time(16, 0)),
		(3, time(16, 0), time(18, 0)),
	),
}

DAY_START = SHIFT_WINDOWS[1][0][1]

# date.weekday() -> Schedule maydoni (yakshanba yo'q)
WEEKDAY_FIELDS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday")

ERROR_MESSAGES = {
	"accuracy": "GPS aniqligi past. Ochiq joyga chiqib qayta urinib ko'ring",
	"location": "Siz amaliyot joyi hududida emassiz",
	"no_face": "Rasmda yuz aniq topilmadi",
	"multiple_faces": "Rasmda faqat bitta yuz bo'lishi kerak",
	"face_small": "Yuz rasmda juda kichik. Kameraga yaqinroq turing",
	"spoof": "Jonli yuz aniqlanmadi",
	"face": "Yuz profil rasmingizga mos kelmadi",
	"no_reference": "Profil rasmingiz topilmadi yoki unda yuz aniqlanmadi. Adminga murojaat qiling",
}


class CheckInError(Exception):
	pass


def shift_for_time(t: time) -> int | None:
	for shift, windows in SHIFT_WINDOWS.items():
		if windows[0][1] <= t < windows[-1][2]:
			return shift
	return None


def step_for_time(shift: int, t: time) -> int | None:
	for step, start, end in SHIFT_WINDOWS[shift]:
		if start <= t < end:
			return step
	return None


# --- jadval ---


def schedules_for(student, day: date):
	"""Talabaning shu kundagi faol jadvallari (shaxsiy jadval guruh jadvalidan ustun)."""
	if day.weekday() >= len(WEEKDAY_FIELDS):
		return Schedule.objects.none()
	group_q = Q(group_id=student.group_id) if student.group_id else Q(pk__in=[])
	return (
		Schedule.objects.filter(
			Q(user=student) | group_q,
			is_active=True,
			start_date__lte=day,
			end_date__gte=day,
			location__is_active=True,
			**{WEEKDAY_FIELDS[day.weekday()]: True},
		)
		.select_related("location")
		.annotate(
			personal=Case(When(user=student, then=Value(0)), default=Value(1), output_field=IntegerField())
		)
		.order_by("personal", "-start_date")
	)


def schedule_for(student, day: date) -> Schedule | None:
	return schedules_for(student, day).first()


def is_schedule_day(schedule: Schedule, day: date) -> bool:
	return (
		schedule.start_date <= day <= schedule.end_date
		and day.weekday() < len(WEEKDAY_FIELDS)
		and getattr(schedule, WEEKDAY_FIELDS[day.weekday()])
	)


def practice_students_by_day(students, schedules, days) -> dict[date, set[int]]:
	"""
	Har bir kun uchun amaliyotga borishi kerak bo'lgan talabalar id'lari (ko'p talaba uchun so'rovsiz hisoblash).
	students - [(id, group_id)], schedules - faol jadvallar ro'yxati.
	"""
	by_group: dict[int, set[int]] = {}
	ids = set()
	for student_id, group_id in students:
		ids.add(student_id)
		by_group.setdefault(group_id, set()).add(student_id)

	result = {}
	for day in days:
		expected = set()
		for schedule in schedules:
			if not is_schedule_day(schedule, day):
				continue
			if schedule.user_id:
				if schedule.user_id in ids:
					expected.add(schedule.user_id)
			elif schedule.group_id:
				expected |= by_group.get(schedule.group_id, set())
		result[day] = expected
	return result


def schedule_weekdays(schedule: Schedule) -> list[int]:
	return [i for i, name in enumerate(WEEKDAY_FIELDS) if getattr(schedule, name)]


# --- lokatsiya ---


LOCATION_TOKEN_SALT = "attendance.location"
LOCATION_TOKEN_MAX_AGE = 5 * 60


def location_area(location: Location):
	"""
	Nuqtalar qaysi tartibda kiritilganidan qat'i nazar to'g'ri ko'pburchak: 4 nuqtaning qavariq qobig'i
	(noto'g'ri tartibda kiritilsa "kapalak" shaklidagi buzuq polygon hosil bo'lmasligi uchun).
	"""
	return MultiPoint(location.polygon()).convex_hull


def check_location(location: Location, lat: float, lng: float) -> bool:
	return location_area(location).covers(Point(lng, lat))


def distance_to_location(location: Location, lat: float, lng: float) -> float:
	"""Nuqtadan hudud chegarasigacha taxminiy masofa (metr), ichida bo'lsa 0."""
	area = location_area(location)
	if area.covers(Point(lng, lat)):
		return 0.0
	# kichik masofalar uchun ekvirektangulyar proyeksiya yetarli
	k = math.cos(math.radians(lat))
	projected = MultiPoint([(x * k, y) for x, y in location.polygon()]).convex_hull
	return projected.distance(Point(lng * k, lat)) * 111_320


@dataclass
class LocationCheck:
	ok: bool
	error_code: str
	message: str
	distance: float
	token: str = ""


def verify_location(student, location: Location, latitude: float, longitude: float, accuracy: float) -> LocationCheck:
	"""Joylashuvni tekshiradi; muvaffaqiyatli bo'lsa check-in uchun qisqa muddatli token beradi."""
	distance = round(distance_to_location(location, latitude, longitude))
	if accuracy > settings.ATTENDANCE["MAX_LOCATION_ACCURACY"]:
		return LocationCheck(False, "accuracy", ERROR_MESSAGES["accuracy"], distance)
	if distance > 0:
		return LocationCheck(
			False, "location", f"Siz amaliyot joyidan ~{distance} m uzoqdasiz ({location.name})", distance
		)
	token = signing.dumps({"u": student.pk, "l": location.pk}, salt=LOCATION_TOKEN_SALT)
	return LocationCheck(True, "", f"Siz amaliyot joyidasiz: {location.name}", 0, token)


def location_token_valid(token: str, student, location: Location) -> bool:
	try:
		data = signing.loads(token, salt=LOCATION_TOKEN_SALT, max_age=LOCATION_TOKEN_MAX_AGE)
	except signing.BadSignature:
		return False
	return data == {"u": student.pk, "l": location.pk}


# --- holat ---


@dataclass
class StepState:
	step: int
	start: time
	end: time
	# passed | available | missed | upcoming
	status: str


@dataclass
class DayState:
	date: date
	now: datetime
	schedule: Schedule | None = None
	attendance: Attendance | None = None
	shift: int | None = None
	shift_locked: bool = False
	current_step: int | None = None
	can_attempt: bool = False
	message: str = ""
	steps: list[StepState] = field(default_factory=list)


def passed_steps(attendance: Attendance | None) -> set[int]:
	if not attendance:
		return set()
	return {s.step for s in attendance.steps.all() if s.success}


def _window_status(step, start, end, passed: set[int], in_own_shift: bool, t: time) -> str:
	if step in passed:
		return "passed"
	if in_own_shift and start <= t < end:
		return "available"
	if t < start:
		return "upcoming"
	return "missed"


def day_steps(passed: set[int], locked_shift: int | None, day: date, now: datetime) -> tuple[int | None, list[StepState]]:
	"""
	Bitta talabaning bitta amaliyot kunidagi qadamlar holati (smena, [StepState x3]).
	locked_shift - muvaffaqiyatli qadam bo'lsa attendance.shift, aks holda None.
	"""
	now = timezone.localtime(now)
	today, t = now.date(), now.time()
	if day != today:
		# o'tgan kun: o'tilmagan qadam - o'tkazilgan; kelajak - kutilmoqda
		shift = locked_shift or 1
		status = "missed" if day < today else "upcoming"
		return locked_shift, [
			StepState(step, start, end, "passed" if step in passed else status)
			for step, start, end in SHIFT_WINDOWS[shift]
		]

	time_shift = shift_for_time(t)
	shift = locked_shift or time_shift or (1 if t < DAY_START else None)
	if shift is None:
		# kun tugadi, smena belgilanmagan - hamma qadam o'tkazilgan
		return None, [StepState(step, start, end, "missed") for step, start, end in SHIFT_WINDOWS[1]]
	in_own_shift = time_shift == shift
	return shift, [
		StepState(step, start, end, _window_status(step, start, end, passed, in_own_shift, t))
		for step, start, end in SHIFT_WINDOWS[shift]
	]


def day_state(student, now: datetime | None = None) -> DayState:
	now = timezone.localtime(now)
	today, t = now.date(), now.time()
	state = DayState(date=today, now=now)

	state.schedule = schedule_for(student, today)
	if not state.schedule:
		state.message = "Bugun amaliyot kuni emas"
		return state

	state.attendance = (
		Attendance.objects.filter(student=student, schedule=state.schedule, date=today)
		.prefetch_related("steps")
		.first()
	)
	passed = passed_steps(state.attendance)
	# smena faqat muvaffaqiyatli qadamdan keyin qulflanadi
	locked = state.attendance.shift if passed else None
	time_shift = shift_for_time(t)

	state.shift_locked = locked is not None
	state.shift = locked or time_shift or (1 if t < DAY_START else None)
	if state.shift is None:
		state.message = "Bugungi amaliyot vaqti tugadi"
		return state

	in_own_shift = time_shift == state.shift
	_, state.steps = day_steps(passed, locked, today, now)

	if time_shift is None:
		state.message = "Amaliyot 08:00 da boshlanadi" if t < DAY_START else "Bugungi amaliyot vaqti tugadi"
		return state
	if not in_own_shift:
		state.message = f"Siz bugun {locked}-smenada tasdiqlagansiz"
		return state

	state.current_step = step_for_time(time_shift, t)
	if state.current_step in passed:
		state.message = f"{state.current_step}-qadam tasdiqlangan. Keyingi qadamni kuting"
		return state

	state.can_attempt = True
	state.message = f"{state.current_step}-qadamni tasdiqlashingiz mumkin"
	return state


# --- tasdiqlash ---


def check_in(
	student, *, latitude, longitude, accuracy, image, location_token, user_agent="", ip_address=None
):
	"""
	Location + FaceID tekshiruvi. Har bir urinish (muvaffaqiyatsizi ham) AttendanceAttempt sifatida saqlanadi.
	Joylashuv ikki marta tekshiriladi: oldindan (location_token) va shu so'rovdagi koordinata bo'yicha.
	Joylashuv o'tmasa FaceID umuman ishga tushmaydi.
	Qaytaradi: AttendanceAttempt
	"""
	state = day_state(student)
	if not state.can_attempt:
		raise CheckInError(state.message)

	shift, step = state.shift, state.current_step
	location = state.schedule.location

	if not location_token_valid(location_token, student, location):
		raise CheckInError("Avval joylashuvingizni aniqlang")

	location_check = verify_location(student, location, latitude, longitude, accuracy)
	location_ok = location_check.ok
	error_code = location_check.error_code

	face_result = face.FaceResult("skipped")
	if not error_code:
		image.seek(0)
		try:
			face_result = face.verify(student, face.load_image(image))
		except face.NoReferenceImage:
			face_result = face.FaceResult("no_reference")
		if face_result.result != "success":
			error_code = face_result.result

	with transaction.atomic():
		attendance, created = Attendance.objects.select_for_update().get_or_create(
			student=student,
			schedule=state.schedule,
			date=state.date,
			defaults={"shift": shift},
		)
		has_success = attendance.steps.filter(success=True).exists()
		if attendance.shift != shift:
			# parallel so'rov boshqa smenada tasdiqlab ulgurgan bo'lishi mumkin
			if has_success:
				raise CheckInError(f"Siz bugun {attendance.shift}-smenada tasdiqlagansiz")
			attendance.shift = shift
			attendance.save(update_fields=["shift"])

		step_obj, _ = AttendanceStep.objects.get_or_create(attendance=attendance, step=step)
		step_obj = AttendanceStep.objects.select_for_update().get(pk=step_obj.pk)
		if step_obj.success:
			raise CheckInError(f"{step}-qadam allaqachon tasdiqlangan")

		success = not error_code
		image.seek(0)
		attempt = AttendanceAttempt(
			step=step_obj,
			ip_address=ip_address,
			latitude=round(latitude, 15),
			longitude=round(longitude, 15),
			location=location,
			face_verified=face_result.result == "success",
			location_verified=location_ok,
			liveness_verified=face_result.liveness,
			success=success,
			error_code=error_code,
			error_message=ERROR_MESSAGES.get(error_code, ""),
			face_distance=face_result.distance,
			face_threshold=face_result.threshold,
			user_agent=user_agent[:1000],
		)
		attempt.image.save(f"{student.uuid}.jpg", image, save=False)
		attempt.save()

		if success:
			step_obj.success = True
			step_obj.save(update_fields=["success"])

	return attempt
