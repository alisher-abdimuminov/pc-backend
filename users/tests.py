import json
import re
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import AuditLog, Group, User

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
TMP_MEDIA = tempfile.mkdtemp()


def example_json(name: str) -> dict:
	"""examples/*.md ichidagi ```json blokini o'qiydi."""
	text = (EXAMPLES / name).read_text()
	return json.loads(re.search(r"```json\s*(.*?)```", text, re.S).group(1))


LOGIN_OK = example_json("hemis-student-login.md")
ME_OK = example_json("hemis-student-me.md")
LOGIN_FAIL = {"success": False, "error": "Login yoki parol xato", "data": [], "code": 401}
TEACHER_LOGIN_OK = example_json("hemis-teacher-login.md")
TEACHER_LOGIN_FAIL = {"ok": False, "status_code": 401, "description": "Login yoki parol noto'g'ri"}
TEACHER_ME = example_json("hemis-teacher-me.md")
# misolda maydonlar "string" placeholder - real ko'rinishdagi qiymatlar bilan to'ldiramiz
TEACHER_ME["result"]["user"].update(
	{
		"id": 55,
		"full_name": "KARIMOV ALISHER BAXTIYOROVICH",
		"login": "tutor_login",
		"telephone": "+998901234567",
		"image": "https://hemis.samdpi.uz/static/crop/tutor.jpg",
		"employee": None,
		"groups": [{"id": 980, "name": "105_rus"}, {"id": 981, "name": "106_rus"}, {}],
	}
)


class FakeResponse:
	def __init__(self, status, body=None, content=b""):
		self.url = ""
		self.text = json.dumps(body) if body is not None else ""
		self.status_code = status
		self._body = body
		self.content = content
		self.ok = 200 <= status < 300

	def json(self):
		return self._body

	def raise_for_status(self):
		if not self.ok:
			import requests

			raise requests.HTTPError(str(self.status_code))


def fake_hemis(password_ok="secret", tutor_password="tutorpass"):
	def post(url, json=None, **kwargs):
		if url.endswith("ver1/tutor/auth/login"):
			if json["login"] == "tutor_login" and json["password"] == tutor_password:
				return FakeResponse(200, TEACHER_LOGIN_OK)
			return FakeResponse(401, TEACHER_LOGIN_FAIL)
		if url.endswith("v1/auth/login"):
			if json["login"] == 320261100667 and json["password"] == password_ok:
				return FakeResponse(200, LOGIN_OK)
			return FakeResponse(401, LOGIN_FAIL)
		return FakeResponse(404, {})

	def get(url, headers=None, **kwargs):
		if url.endswith("ver1/tutor/data/get-me"):
			return FakeResponse(200, TEACHER_ME)
		if url.endswith("v1/account/me"):
			return FakeResponse(200, ME_OK)
		if url.endswith(".jpg"):
			return FakeResponse(200, content=b"\xff\xd8\xff")
		return FakeResponse(404, {})

	return mock.patch.multiple("users.hemis.requests", post=mock.DEFAULT, get=mock.DEFAULT), post, get


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class HemisTestCase(TestCase):
	@classmethod
	def tearDownClass(cls):
		super().tearDownClass()
		shutil.rmtree(TMP_MEDIA, ignore_errors=True)

	def setUp(self):
		patcher, post, get = fake_hemis()
		mocks = patcher.start()
		mocks["post"].side_effect = post
		mocks["get"].side_effect = get
		self.post, self.get = mocks["post"], mocks["get"]
		self.addCleanup(patcher.stop)
		self.client = APIClient()

	def login(self, login="320261100667", password="secret"):
		return self.client.post("/api/auth/login/", {"login": login, "password": password}, format="json")


class StudentLoginTests(HemisTestCase):
	def test_new_student_created_from_hemis(self):
		response = self.login()
		self.assertEqual(response.status_code, 200, response.data)
		user = User.objects.get(username="320261100667")
		self.assertEqual(user.role, "student")
		self.assertEqual(user.full_name, "RABBIMOVA DILNOZA ZOHIDJON QIZI")
		self.assertEqual(user.group.name, ME_OK["data"]["group"]["name"])
		self.assertEqual(user.group.hemis_id, 980)
		self.assertEqual(user.faculty.name, "Tillar")
		self.assertEqual(user.group.faculty, user.faculty)
		self.assertEqual(user.level, "1-kurs")
		self.assertEqual(user.semester, "1-semestr")
		self.assertEqual(user.gender, "Ayol")
		self.assertEqual(user.gpa, 0.0)
		self.assertTrue(user.image)
		self.assertTrue(user.check_password("secret"))
		self.assertIn("access", response.data)

	def test_existing_student_classic_login_without_hemis(self):
		self.login()
		self.post.reset_mock()
		response = self.login()
		self.assertEqual(response.status_code, 200)
		self.post.assert_not_called()

	def test_wrong_password(self):
		response = self.login(password="bad")
		self.assertEqual(response.status_code, 401)
		self.assertFalse(User.objects.exists())

	def test_password_changed_in_hemis(self):
		self.login()
		user = User.objects.get()
		user.set_password("old")
		user.save()
		response = self.login()
		self.assertEqual(response.status_code, 200)
		user.refresh_from_db()
		self.assertTrue(user.check_password("secret"))

	def test_login_sent_as_number(self):
		self.login()
		self.assertEqual(self.post.call_args_list[0].kwargs["json"]["login"], 320261100667)

	def test_wrong_password_tries_teacher_and_reports_auth_error(self):
		response = self.login(password="bad")
		self.assertEqual(response.status_code, 401)
		urls = [c.args[0] for c in self.post.call_args_list]
		self.assertTrue(urls[0].endswith("v1/auth/login"))
		self.assertTrue(urls[1].endswith("ver1/tutor/auth/login"))

	def test_admin_never_goes_to_hemis(self):
		User.objects.create_superuser("admin", "adminpass")
		self.assertEqual(self.login("admin", "adminpass").status_code, 200)
		self.assertEqual(self.login("admin", "secret").status_code, 401)
		self.post.assert_not_called()


class TeacherLoginTests(HemisTestCase):
	def test_new_teacher_created_from_hemis(self):
		response = self.login("tutor_login", "tutorpass")
		self.assertEqual(response.status_code, 200, response.data)
		self.assertEqual(response.data["user"]["role"], "teacher")

		user = User.objects.get(username="tutor_login")
		self.assertEqual(user.role, "teacher")
		self.assertEqual(user.full_name, "KARIMOV ALISHER BAXTIYOROVICH")
		self.assertEqual((user.second_name, user.first_name, user.third_name), ("KARIMOV", "ALISHER", "BAXTIYOROVICH"))
		self.assertEqual(user.short_name, "KARIMOV A. B.")
		self.assertEqual(user.phone, "+998901234567")
		self.assertTrue(user.image)
		self.assertIsNone(user.group)

		# login string bo'lib yuboriladi, avval talaba endpointi sinalgan
		calls = self.post.call_args_list
		self.assertTrue(calls[0].args[0].endswith("v1/auth/login"))
		self.assertEqual(calls[1].kwargs["json"]["login"], "tutor_login")

	def test_teacher_groups_linked(self):
		existing = Group.objects.create(name="eski nom", hemis_id=980)
		self.login("tutor_login", "tutorpass")
		teacher = User.objects.get(username="tutor_login")
		existing.refresh_from_db()
		self.assertEqual(existing.teacher, teacher)
		self.assertEqual(existing.name, "105_rus")
		self.assertEqual(set(teacher.teaching_groups.values_list("hemis_id", flat=True)), {980, 981})

	def test_existing_teacher_goes_only_to_tutor_endpoint(self):
		self.login("tutor_login", "tutorpass")
		user = User.objects.get(username="tutor_login")
		user.set_password("old")
		user.save()
		self.post.reset_mock()
		self.assertEqual(self.login("tutor_login", "tutorpass").status_code, 200)
		self.assertEqual(len(self.post.call_args_list), 1)
		self.assertTrue(self.post.call_args_list[0].args[0].endswith("ver1/tutor/auth/login"))

	def test_teacher_wrong_password(self):
		self.assertEqual(self.login("tutor_login", "bad").status_code, 401)
		self.assertFalse(User.objects.exists())


class ManagementTests(TestCase):
	def setUp(self):
		self.admin = User.objects.create_superuser("admin", "x")
		self.group = Group.objects.create(name="101")
		self.teacher = User.objects.create_user("t1", "x", role="teacher", full_name="KARIMOV A.")
		self.student = User.objects.create_user("s1", "pass", role="student", group=self.group)
		self.client = APIClient()
		self.client.force_authenticate(self.admin)

	def test_assign_teacher(self):
		url = f"/api/auth/groups/{self.group.uuid}/teacher/"
		response = self.client.patch(url, {"teacher_uuid": str(self.teacher.uuid)}, format="json")
		self.assertEqual(response.status_code, 200, response.data)
		self.group.refresh_from_db()
		self.assertEqual(self.group.teacher, self.teacher)
		self.assertTrue(AuditLog.objects.filter(changes__teacher=[None, "KARIMOV A."]).exists())

		# olib tashlash
		self.client.patch(url, {"teacher_uuid": None}, format="json")
		self.group.refresh_from_db()
		self.assertIsNone(self.group.teacher)

		# talabani o'qituvchi qilib bo'lmaydi
		response = self.client.patch(url, {"teacher_uuid": str(self.student.uuid)}, format="json")
		self.assertEqual(response.status_code, 404)

		teachers = self.client.get("/api/auth/teachers/", {"search": "karim"}).data
		self.assertEqual([t["username"] for t in teachers], ["t1"])

	def test_teacher_cannot_manage(self):
		self.client.force_authenticate(self.teacher)
		self.assertEqual(
			self.client.patch(f"/api/auth/groups/{self.group.uuid}/teacher/", {"teacher_uuid": None}, format="json").status_code,
			403,
		)
		self.assertEqual(
			self.client.post(f"/api/auth/students/{self.student.uuid}/status/", {"is_active": False, "reason": "x"}).status_code,
			403,
		)

	def test_block_student(self):
		# talaba tizimda - tokeni bor
		login = APIClient().post("/api/auth/login/", {"login": "s1", "password": "pass"}, format="json")
		access, refresh = login.data["access"], login.data["refresh"]

		url = f"/api/auth/students/{self.student.uuid}/status/"
		self.assertEqual(self.client.post(url, {"is_active": False}).status_code, 400)  # sababsiz
		response = self.client.post(url, {"is_active": False, "reason": "Boshqa odam rasmi"})
		self.assertEqual(response.status_code, 200)
		self.student.refresh_from_db()
		self.assertFalse(self.student.is_active)

		# login, mavjud access va refresh token - hammasi ishlamaydi
		self.assertEqual(APIClient().post("/api/auth/login/", {"login": "s1", "password": "pass"}, format="json").status_code, 403)
		other = APIClient()
		other.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
		self.assertEqual(other.get("/api/auth/me/").status_code, 401)
		self.assertEqual(APIClient().post("/api/auth/refresh/", {"refresh": refresh}).status_code, 401)

		history = self.client.get(f"{url}history/").data
		self.assertEqual(history[0]["reason"], "Boshqa odam rasmi")
		self.assertFalse(history[0]["is_active"])

		# qayta faollashtirish
		self.client.post(url, {"is_active": True, "reason": ""})
		self.student.refresh_from_db()
		self.assertTrue(self.student.is_active)
		self.assertEqual(APIClient().post("/api/auth/login/", {"login": "s1", "password": "pass"}, format="json").status_code, 200)


class LittleRoleAndAuditTests(TestCase):
	def setUp(self):
		self.admin = User.objects.create_superuser("admin", "adminpass")
		self.admin_client = APIClient()
		self.admin_client.force_authenticate(self.admin)

	def create_little(self, permissions=()):
		response = self.admin_client.post(
			"/api/auth/staff/",
			{"username": "little1", "password": "secret1", "full_name": "Kichik Admin", "permissions": list(permissions)},
			format="json",
		)
		self.assertEqual(response.status_code, 201, response.data)
		return User.objects.get(username="little1"), response

	def client_for(self, user):
		user = User.objects.get(pk=user.pk)  # permission keshi tozalanadi
		client = APIClient()
		client.force_authenticate(user)
		return client

	def test_little_without_permissions_sees_only_dashboard(self):
		little, _ = self.create_little()
		self.assertEqual(little.role, "little")
		client = self.client_for(little)
		self.assertEqual(client.get("/api/auth/me/").data["permissions"], [])
		self.assertEqual(client.get("/api/attendance/dashboard/").status_code, 200)
		for url in (
			"/api/attendance/locations/",
			"/api/attendance/schedules/",
			"/api/attendance/groups/",
			"/api/attendance/attempts/",
			"/api/assignments/",
			"/api/auth/audit-logs/",
			"/api/auth/staff/",
		):
			self.assertEqual(client.get(url).status_code, 403, url)

	def test_little_with_location_permissions(self):
		little, _ = self.create_little(["attendance.view_location", "attendance.add_location"])
		client = self.client_for(little)
		self.assertEqual(
			sorted(client.get("/api/auth/me/").data["permissions"]),
			["attendance.add_location", "attendance.view_location"],
		)
		self.assertEqual(client.get("/api/attendance/locations/").status_code, 200)
		data = {
			"name": "5-maktab",
			"point_1": "39.654,66.975",
			"point_2": "39.655,66.975",
			"point_3": "39.655,66.976",
			"point_4": "39.654,66.976",
		}
		response = client.post("/api/attendance/locations/", data)
		self.assertEqual(response.status_code, 201, response.data)
		uuid = response.data["uuid"]
		# tahrirlash / o'chirish berilmagan
		self.assertEqual(client.patch(f"/api/attendance/locations/{uuid}/", {"name": "x"}).status_code, 403)
		self.assertEqual(client.delete(f"/api/attendance/locations/{uuid}/").status_code, 403)
		self.assertEqual(client.get("/api/attendance/schedules/").status_code, 403)

		# admin permission'ni olib tashlasa - darhol yopiladi
		self.admin_client.patch(f"/api/auth/staff/{little.uuid}/", {"permissions": []}, format="json")
		self.assertEqual(self.client_for(little).get("/api/attendance/locations/").status_code, 403)

	def test_staff_api_admin_only_and_validation(self):
		little, _ = self.create_little()
		self.assertEqual(self.client_for(little).get("/api/auth/staff/").status_code, 403)
		response = self.admin_client.post(
			"/api/auth/staff/", {"username": "x2", "password": "secret1", "full_name": "X", "permissions": ["auth.delete_user"]}, format="json"
		)
		self.assertEqual(response.status_code, 400)
		self.assertFalse(User.objects.filter(username="x2").exists())
		catalog = self.admin_client.get("/api/auth/permissions/").data
		self.assertIn("attendance.add_location", [p["code"] for p in catalog])

	def test_audit_logs_crud_with_request_context(self):
		response = self.admin_client.post(
			"/api/attendance/locations/",
			{"name": "7-maktab", "point_1": "1,1", "point_2": "1,2", "point_3": "2,2", "point_4": "2,1"},
			REMOTE_ADDR="10.0.0.5",
			HTTP_USER_AGENT="pytest",
		)
		uuid = response.data["uuid"]
		self.admin_client.patch(f"/api/attendance/locations/{uuid}/", {"name": "7-maktab (yangi)"})
		self.admin_client.delete(f"/api/attendance/locations/{uuid}/")

		logs = AuditLog.objects.filter(content_type__model="location").order_by("created_at")
		self.assertEqual([log.action for log in logs], ["CREATE", "UPDATE", "DELETE"])
		create, update, delete = logs
		self.assertEqual(create.user, self.admin)
		self.assertEqual(create.ip_address, "10.0.0.5")
		self.assertEqual(create.user_agent, "pytest")
		self.assertEqual(create.method, "POST")
		self.assertEqual(update.changes["name"], ["7-maktab", "7-maktab (yangi)"])
		self.assertNotIn("updated_at", update.changes)
		self.assertEqual(delete.changes["deleted"]["name"], "7-maktab (yangi)")

		# API: filtr va ruxsat
		data = self.admin_client.get("/api/auth/audit-logs/", {"model": "attendance.location", "action": "UPDATE"}).data
		self.assertEqual(data["count"], 1)
		self.assertEqual(data["results"][0]["user"]["username"], "admin")

	def test_login_logout_and_secrets(self):
		User.objects.create_user("staff1", "goodpass", role="little")
		self.assertEqual(APIClient().post("/api/auth/login/", {"login": "staff1", "password": "bad"}, format="json").status_code, 401)
		response = APIClient().post("/api/auth/login/", {"login": "staff1", "password": "goodpass"}, format="json")
		client = APIClient()
		client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
		self.assertEqual(client.post("/api/auth/logout/").status_code, 204)

		logins = AuditLog.objects.filter(action="LOGIN").order_by("created_at")
		self.assertEqual([log.changes["success"] for log in logins], [False, True])
		self.assertEqual(logins[0].changes["reason"], "wrong_password")
		self.assertTrue(AuditLog.objects.filter(action="LOGOUT", user__username="staff1").exists())

		# parol hech qachon ochiq yozilmaydi
		created = AuditLog.objects.get(action="CREATE", object_repr="staff1")
		self.assertEqual(created.changes["password"], ["***", "***"])
