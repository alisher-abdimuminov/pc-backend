from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
import shutil
import tempfile

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from users.models import Group, User


TMP_MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class AssignmentTests(TestCase):
	@classmethod
	def tearDownClass(cls):
		super().tearDownClass()
		shutil.rmtree(TMP_MEDIA, ignore_errors=True)

	def setUp(self):
		self.teacher = User.objects.create_user("t1", "x", role="teacher")
		self.group = Group.objects.create(name="101", teacher=self.teacher)
		self.other_group = Group.objects.create(name="102")
		self.student = User.objects.create_user("s1", "x", role="student", group=self.group)
		self.client = APIClient()

	def create(self, **extra):
		self.client.force_authenticate(self.teacher)
		data = {
			"title": "Dars ishlanmasi",
			"deadline": (timezone.now() + timedelta(days=3)).isoformat(),
			"group_uuids": [str(self.group.uuid)],
			**extra,
		}
		return self.client.post("/api/assignments/", data, format="multipart")

	def test_flow(self):
		response = self.create()
		self.assertEqual(response.status_code, 201, response.data)
		uuid = response.data["uuid"]

		self.client.force_authenticate(self.student)
		listing = self.client.get("/api/assignments/").data["results"]
		self.assertEqual(len(listing), 1)
		self.assertIsNone(listing[0]["my_submission"])
		response = self.client.post(
			f"/api/assignments/{uuid}/submit/",
			{"file": SimpleUploadedFile("a.pdf", b"x")},
			format="multipart",
		)
		self.assertEqual(response.status_code, 201, response.data)
		submission = response.data["uuid"]

		self.client.force_authenticate(self.teacher)
		rows = self.client.get(f"/api/assignments/{uuid}/submissions/").data
		self.assertEqual(rows[0]["submission"]["uuid"], submission)
		response = self.client.post(f"/api/submissions/{submission}/grade/", {"grade": 90, "feedback": "Yaxshi"})
		self.assertEqual(response.status_code, 200, response.data)
		self.assertEqual(response.data["grade"], 90)

		self.client.force_authenticate(self.student)
		response = self.client.post(
			f"/api/assignments/{uuid}/submit/",
			{"file": SimpleUploadedFile("b.pdf", b"y")},
			format="multipart",
		)
		self.assertEqual(response.status_code, 400)

	def test_teacher_cannot_assign_foreign_group(self):
		response = self.create(group_uuids=[str(self.other_group.uuid)])
		self.assertEqual(response.status_code, 400)

	def test_student_cannot_create(self):
		self.client.force_authenticate(self.student)
		self.assertEqual(self.client.post("/api/assignments/", {}).status_code, 403)
