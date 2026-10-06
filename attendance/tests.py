import io
import time
from datetime import date, datetime
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
import shutil
import tempfile

from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from users.models import Group, User

from . import face
from .models import AttendanceAttempt, Location, Schedule
from .services import CheckInError, check_in, day_state, verify_location

# 2026-10-02 - juma
FRIDAY = date(2026, 10, 2)
INSIDE = (39.6545, 66.9755)
OUTSIDE = (39.7, 67.0)


def at(hour, minute=0, day=FRIDAY):
	return timezone.make_aware(datetime(day.year, day.month, day.day, hour, minute))


def photo():
	buf = io.BytesIO()
	Image.new("RGB", (10, 10)).save(buf, "JPEG")
	return SimpleUploadedFile("p.jpg", buf.getvalue(), content_type="image/jpeg")


TMP_MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class AttendanceTests(TestCase):
	@classmethod
	def tearDownClass(cls):
		super().tearDownClass()
		shutil.rmtree(TMP_MEDIA, ignore_errors=True)

	def setUp(self):
		self.group = Group.objects.create(name="101")
		self.student = User.objects.create_user("s1", "x", role="student", group=self.group)
		self.location = Location.objects.create(
			name="1-maktab",
			point_1="39.654,66.975",
			point_2="39.655,66.975",
			point_3="39.655,66.976",
			point_4="39.654,66.976",
		)
		Schedule.objects.create(
			name="Jadval",
			group=self.group,
			location=self.location,
			start_date=date(2026, 9, 1),
			end_date=date(2026, 12, 31),
			friday=True,
			saturday=True,
		)
		patcher = mock.patch.object(face, "verify", return_value=face.FaceResult("success", 0.2, 0.68, True))
		self.verify = patcher.start()
		self.addCleanup(patcher.stop)

	def token(self, location=None):
		return verify_location(self.student, location or self.location, *INSIDE, accuracy=10).token

	def attempt(self, when, point=INSIDE, accuracy=10, token=None):
		with mock.patch("django.utils.timezone.now", return_value=when):
			return check_in(
				self.student,
				latitude=point[0],
				longitude=point[1],
				accuracy=accuracy,
				image=photo(),
				location_token=self.token() if token is None else token,
			)

	def state(self, when):
		return day_state(self.student, when)

	def test_not_practice_day(self):
		state = self.state(at(9, day=date(2026, 10, 5)))  # dushanba
		self.assertFalse(state.can_attempt)
		self.assertIsNone(state.schedule)

	def test_steps_by_time(self):
		state = self.state(at(10, 30))
		self.assertEqual((state.shift, state.current_step), (1, 2))
		self.assertEqual([s.status for s in state.steps], ["missed", "available", "upcoming"])

		state = self.state(at(7))
		self.assertFalse(state.can_attempt)
		self.assertEqual([s.status for s in state.steps], ["upcoming"] * 3)

		state = self.state(at(13, 30))
		self.assertEqual((state.shift, state.current_step), (2, 1))

		self.assertIsNone(self.state(at(18, 5)).shift)

	def test_morning_success_locks_shift_1(self):
		attempt = self.attempt(at(8, 30))
		self.assertTrue(attempt.success)
		self.assertEqual(attempt.step.attendance.shift, 1)

		with self.assertRaises(CheckInError):
			self.attempt(at(9, 0))  # 1-qadam allaqachon o'tilgan

		self.assertTrue(self.attempt(at(12, 30)).success)  # 3-qadam

		state = self.state(at(14))
		self.assertFalse(state.can_attempt)
		self.assertEqual(state.shift, 1)
		self.assertEqual([s.status for s in state.steps], ["passed", "missed", "passed"])
		with self.assertRaises(CheckInError):
			self.attempt(at(14))

	def test_failed_morning_attempt_does_not_lock_shift(self):
		attempt = self.attempt(at(12, 50), OUTSIDE)
		self.assertFalse(attempt.success)
		self.assertEqual(attempt.error_code, "location")
		self.verify.assert_not_called()

		attempt = self.attempt(at(13, 10))
		self.assertTrue(attempt.success)
		self.assertEqual(attempt.step.attendance.shift, 2)

	def test_face_mismatch(self):
		self.verify.return_value = face.FaceResult("face", 0.9, 0.68, True)
		attempt = self.attempt(at(15))
		self.assertFalse(attempt.success)
		self.assertTrue(attempt.location_verified)
		self.assertEqual(attempt.error_code, "face")
		# muvaffaqiyatsiz urinishdan keyin qayta urinish mumkin
		self.assertTrue(self.state(at(15, 1)).can_attempt)

	def test_personal_schedule_overrides_group(self):
		other = Location.objects.create(
			name="2-maktab", point_1="1,1", point_2="1,2", point_3="2,2", point_4="2,1"
		)
		Schedule.objects.create(
			name="Shaxsiy",
			user=self.student,
			location=other,
			start_date=date(2026, 9, 1),
			end_date=date(2026, 12, 31),
			friday=True,
		)
		self.assertEqual(self.state(at(9)).schedule.location, other)
		# guruh joyi uchun olingan token shaxsiy jadval joyida yaroqsiz
		with self.assertRaises(CheckInError):
			self.attempt(at(9))
		other_token = verify_location(self.student, other, 1.5, 1.5, accuracy=10).token
		self.assertEqual(self.attempt(at(9), token=other_token).error_code, "location")

	def test_no_location_token_no_attempt(self):
		with self.assertRaises(CheckInError):
			self.attempt(at(9), token="")
		with self.assertRaises(CheckInError):
			self.attempt(at(9), token="soxta.token")
		other = User.objects.create_user("s2", "x", role="student", group=self.group)
		foreign = verify_location(other, self.location, *INSIDE, accuracy=10).token
		with self.assertRaises(CheckInError):
			self.attempt(at(9), token=foreign)
		self.assertFalse(AttendanceAttempt.objects.exists())
		self.verify.assert_not_called()

	def test_expired_location_token(self):
		token = self.token()
		with mock.patch("django.core.signing.time.time", return_value=time.time() + 6 * 60):
			with self.assertRaises(CheckInError):
				self.attempt(at(9), token=token)

	def test_outside_location_never_runs_face(self):
		# token bor, lekin rasm yuborilayotgan paytda hududdan chiqib ketgan
		attempt = self.attempt(at(9), OUTSIDE)
		self.assertFalse(attempt.success)
		self.assertFalse(attempt.location_verified)
		self.assertFalse(attempt.face_verified)
		self.verify.assert_not_called()

	def test_low_accuracy_rejected(self):
		attempt = self.attempt(at(9), accuracy=500)
		self.assertEqual(attempt.error_code, "accuracy")
		self.verify.assert_not_called()
		self.assertFalse(verify_location(self.student, self.location, *INSIDE, accuracy=500).ok)

	def test_points_in_any_order(self):
		# nuqtalar "kapalak" tartibida kiritilgan: 1-3-2-4
		self.location.point_2, self.location.point_3 = self.location.point_3, self.location.point_2
		self.location.save()
		self.assertTrue(verify_location(self.student, self.location, *INSIDE, accuracy=10).ok)
		self.assertTrue(verify_location(self.student, self.location, 39.6541, 66.9759, accuracy=10).ok)

	def test_location_check_api(self):
		client = APIClient()
		client.force_authenticate(self.student)
		with mock.patch("django.utils.timezone.now", return_value=at(10, 15)):
			response = client.post("/api/attendance/location/", {"latitude": OUTSIDE[0], "longitude": OUTSIDE[1], "accuracy": 10})
			self.assertEqual(response.status_code, 200)
			self.assertFalse(response.data["ok"])
			self.assertIsNone(response.data["token"])
			self.assertGreater(response.data["distance"], 1000)

			response = client.post("/api/attendance/location/", {"latitude": INSIDE[0], "longitude": INSIDE[1]})
			self.assertEqual(response.status_code, 400)  # accuracy majburiy

	def test_api(self):
		client = APIClient()
		client.force_authenticate(self.student)
		with mock.patch("django.utils.timezone.now", return_value=at(10, 15)):
			response = client.get("/api/attendance/today/")
			self.assertEqual(response.status_code, 200)
			self.assertTrue(response.data["can_attempt"])
			response = client.post("/api/attendance/location/", {"latitude": INSIDE[0], "longitude": INSIDE[1], "accuracy": 10})
			self.assertTrue(response.data["ok"])
			token = response.data["token"]
			response = client.post(
				"/api/attendance/check-in/",
				{"latitude": INSIDE[0], "longitude": INSIDE[1], "accuracy": 10, "location_token": token, "image": photo()},
				format="multipart",
			)
			self.assertEqual(response.status_code, 201, response.data)
			self.assertTrue(response.data["attempt"]["success"])
			# talabaga rasm / koordinata / yuz masofasi qaytarilmaydi
			for key in ("image", "latitude", "longitude", "face_distance", "ip_address"):
				self.assertNotIn(key, response.data["attempt"])
			self.assertEqual(response.data["state"]["steps"][1]["status"], "passed")

		teacher = User.objects.create_user("t1", "x", role="teacher")
		self.group.teacher = teacher
		self.group.save()
		client.force_authenticate(teacher)
		response = client.get(f"/api/attendance/groups/{self.group.uuid}/", {"date": "2026-10-02"})
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["students"][0]["passed_steps"], [2])
		response = client.get(f"/api/attendance/groups/{self.group.uuid}/report/", {"from": "2026-09-28", "to": "2026-10-04"})
		self.assertEqual(response.data["days"], [date(2026, 10, 2), date(2026, 10, 3)])
		self.assertEqual(client.get("/api/attendance/check-in/").status_code, 403)

	def staff_client(self):
		teacher = User.objects.filter(username="t_staff").first() or User.objects.create_user("t_staff", "x", role="teacher")
		self.group.teacher = teacher
		self.group.save()
		client = APIClient()
		client.force_authenticate(teacher)
		return client

	def test_group_day_step_statuses(self):
		self.attempt(at(10, 30))  # 2-qadam tasdiqlandi, 1-smena
		client = self.staff_client()
		with mock.patch("django.utils.timezone.now", return_value=at(11)):
			row = client.get(f"/api/attendance/groups/{self.group.uuid}/", {"date": "2026-10-02"}).data["students"][0]
		self.assertEqual(row["steps"], ["missed", "passed", "upcoming"])

		with mock.patch("django.utils.timezone.now", return_value=at(9, day=date(2026, 10, 5))):
			row = client.get(f"/api/attendance/groups/{self.group.uuid}/", {"date": "2026-10-02"}).data["students"][0]
		self.assertEqual(row["steps"], ["missed", "passed", "missed"])
		# amaliyot kuni bo'lmagan sana
		with mock.patch("django.utils.timezone.now", return_value=at(9, day=date(2026, 10, 5))):
			row = client.get(f"/api/attendance/groups/{self.group.uuid}/", {"date": "2026-10-05"}).data["students"][0]
		self.assertIsNone(row["steps"])

	def admin_client(self):
		client = APIClient()
		client.force_authenticate(User.objects.create_superuser("adm", "x"))
		return client

	def test_attempts_list_filters(self):
		self.attempt(at(8, 30))
		self.attempt(at(10, 30), OUTSIDE)
		self.attempt(at(10, 40))
		client = self.admin_client()
		url = "/api/attendance/attempts/"
		self.assertEqual(client.get(url).data["count"], 3)
		self.assertEqual(client.get(url, {"result": "fail"}).data["count"], 1)
		self.assertEqual(client.get(url, {"error_code": "location"}).data["count"], 1)
		self.assertEqual(client.get(url, {"step": "2"}).data["count"], 2)
		self.assertEqual(client.get(url, {"search": "s1"}).data["count"], 3)
		self.assertEqual(client.get(url, {"search": "boshqa"}).data["count"], 0)
		self.assertEqual(client.get(url, {"from": "2026-10-03"}).data["count"], 0)
		page = client.get(url, {"page_size": 2})
		self.assertEqual(len(page.data["results"]), 2)
		self.assertIsNotNone(page.data["next"])
		self.assertEqual(page.data["results"][0]["student"]["username"], "s1")

	def test_only_admin_and_permitted_little_see_attempts(self):
		self.attempt(at(10, 30))
		dean = User.objects.create_user("dean1", "x", role="dean")
		little = User.objects.create_user("little1", "x", role="little")
		for user in (self.staff_client(), dean, little):
			client = user if isinstance(user, APIClient) else APIClient()
			if not isinstance(user, APIClient):
				client.force_authenticate(user)
			self.assertEqual(client.get("/api/attendance/attempts/").status_code, 403)

		# o'qituvchi talaba sahifasida faqat "keldi/kelmadi"ni ko'radi - rasm / GPS yo'q
		client = self.staff_client()
		data = client.get(f"/api/attendance/students/{self.student.uuid}/").data
		self.assertFalse(data["can_view_attempts"])
		self.assertEqual(data["attendances"][0]["passed_steps"], [2])
		self.assertEqual(data["attendances"][0]["steps"][0], {**data["attendances"][0]["steps"][0], "step": 2, "success": True})
		self.assertNotIn("attempts", data["attendances"][0]["steps"][0])

		# ruxsat berilgan little - ko'radi
		from django.contrib.auth.models import Permission

		little.user_permissions.add(
			Permission.objects.get(codename="view_attendanceattempt"),
			Permission.objects.get(codename="view_attendance"),
		)
		client = APIClient()
		client.force_authenticate(User.objects.get(pk=little.pk))
		self.assertEqual(client.get("/api/attendance/attempts/").data["count"], 1)
		data = client.get(f"/api/attendance/students/{self.student.uuid}/").data
		self.assertTrue(data["can_view_attempts"])
		self.assertIn("image", data["attendances"][0]["steps"][0]["attempts"][0])

	def test_teacher_has_only_own_groups_attendance_and_assignments(self):
		client = self.staff_client()
		me = client.get("/api/auth/me/").data
		self.assertEqual(
			sorted(me["permissions"]),
			["assignments.view_assignment", "attendance.view_attendance", "users.view_group"],
		)
		for url in ("/api/attendance/schedules/", "/api/attendance/locations/", "/api/auth/students/", "/api/auth/audit-logs/"):
			self.assertEqual(client.get(url).status_code, 403, url)
		# boshqa guruh davomati ko'rinmaydi
		other_group = Group.objects.create(name="999")
		self.assertEqual(client.get(f"/api/attendance/groups/{other_group.uuid}/").status_code, 404)

	def test_dashboard(self):
		User.objects.create_user("s2", "x", role="student", group=self.group)
		# boshqa guruh talabasi o'qituvchi dashboard'iga kirmasligi kerak
		other_group = Group.objects.create(name="999")
		User.objects.create_user("s3", "x", role="student", group=other_group)
		Schedule.objects.create(
			name="Boshqa", group=other_group, location=self.location,
			start_date=date(2026, 9, 1), end_date=date(2026, 12, 31), friday=True,
		)
		self.attempt(at(8, 30))
		self.attempt(at(10, 30), OUTSIDE)

		teacher = self.staff_client()
		with mock.patch("django.utils.timezone.now", return_value=at(11)):
			data = teacher.get("/api/attendance/dashboard/").data
		self.assertEqual(data["today"], {"expected": 2, "came": 1, "full": 0})
		self.assertEqual(data["totals"]["students"], 2)
		self.assertIsNone(data["attempts_today"])
		self.assertEqual(data["recent_failures"], [])
		self.assertEqual(data["assignments"], {"active": 0, "submitted": 0, "ungraded": 0})

		client = self.admin_client()
		with mock.patch("django.utils.timezone.now", return_value=at(11)):
			data = client.get("/api/attendance/dashboard/").data
		self.assertEqual(data["today"]["expected"], 3)
		self.assertEqual(data["attempts_today"]["success"], 1)
		self.assertEqual(data["attempts_today"]["failed"], 1)
		self.assertEqual(data["attempts_today"]["by_error"][0]["code"], "location")
		self.assertEqual(len(data["trend"]), 14)
		self.assertEqual(data["trend"][-1]["came"], 1)
		self.assertEqual(len(data["groups"]), 2)
		self.assertEqual(len(data["recent_failures"]), 1)


class SelfieProblemTests(TestCase):
	@staticmethod
	def face(w, h=None, confidence=0.99):
		return {"facial_area": {"x": 0, "y": 0, "w": w, "h": h or w}, "confidence": confidence}

	def test_ok(self):
		self.assertEqual(face.selfie_problem([self.face(400)], image_width=1280), "")

	def test_second_big_face(self):
		self.assertEqual(face.selfie_problem([self.face(400), self.face(250)], 1280), "multiple_faces")

	def test_tiny_background_face_ignored(self):
		self.assertEqual(face.selfie_problem([self.face(400), self.face(60)], 1280), "")

	def test_low_confidence(self):
		self.assertEqual(face.selfie_problem([self.face(400, confidence=0.5)], 1280), "no_face")

	def test_face_too_small(self):
		self.assertEqual(face.selfie_problem([self.face(120)], 1280), "face_small")


class StudentPrivacyTests(TestCase):
	def test_student_history_endpoints_removed(self):
		student = User.objects.create_user("s1", "x", role="student")
		client = APIClient()
		client.force_authenticate(student)
		self.assertEqual(client.get("/api/attendance/my/attendances/").status_code, 404)
