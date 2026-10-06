from uuid import uuid4

from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from .manager import UserManager

ROLE = (
	("admin", "Admin"),
	("little", "Little"),
	("dean", "Dekan"),
	("teacher", "O'qituvchi"),
	("student", "Talaba"),
)


class Group(models.Model):
	uuid = models.UUIDField(default=uuid4, editable=False, unique=True)
	name = models.CharField(max_length=255)
	hemis_id = models.PositiveIntegerField(
		null=True,
		blank=True,
		unique=True,
	)
	faculty = models.ForeignKey(
		"Faculty",
		null=True,
		blank=True,
		on_delete=models.SET_NULL,
		related_name="groups",
	)
	teacher = models.ForeignKey(
		"User",
		null=True,
		blank=True,
		on_delete=models.SET_NULL,
		related_name="teaching_groups",
		limit_choices_to={"role": "teacher"},
	)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return self.name


class Faculty(models.Model):
	uuid = models.UUIDField(default=uuid4, editable=False, unique=True)
	name = models.CharField(max_length=255)
	hemis_id = models.PositiveIntegerField(
		null=True,
		blank=True,
		unique=True,
	)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return self.name


class User(AbstractUser):
	uuid = models.UUIDField(default=uuid4, editable=False, unique=True)

	first_name = models.CharField(max_length=255, null=True, blank=True)
	second_name = models.CharField(max_length=255, null=True, blank=True)
	third_name = models.CharField(max_length=255, null=True, blank=True)
	full_name = models.CharField(max_length=255, null=True, blank=True)
	short_name = models.CharField(max_length=255, null=True, blank=True)

	image = models.ImageField(upload_to="users/%Y/%m/", null=True, blank=True)
	hemis_image_url = models.URLField(max_length=1000, blank=True)
	birth_date = models.CharField(max_length=50, blank=True)
	phone = models.CharField(max_length=255, null=True, blank=True)
	passport_pin = models.CharField(max_length=255, null=True, blank=True)
	passport_number = models.CharField(max_length=255, null=True, blank=True)
	gender = models.CharField(max_length=10, null=True, blank=True)

	payment_form = models.CharField(max_length=100, blank=True)
	group = models.ForeignKey(
		"Group",
		null=True,
		blank=True,
		on_delete=models.SET_NULL,
		related_name="students",
	)
	faculty = models.ForeignKey(
		"Faculty",
		null=True,
		blank=True,
		on_delete=models.SET_NULL,
		related_name="students",
	)
	level = models.CharField(max_length=100, blank=True)
	semester = models.CharField(max_length=100, blank=True)
	gpa = models.FloatField(null=True, blank=True, help_text="HEMIS GPA")

	address = models.CharField(max_length=100, blank=True)
	country = models.CharField(max_length=100, blank=True)
	province = models.CharField(max_length=100, blank=True)
	district = models.CharField(max_length=100, blank=True)

	role = models.CharField(max_length=10, choices=ROLE, default="student")
	# yuz tasdiqlash uchun etalon rasm embeddingi (image o'zgarsa tozalanadi)
	face_embedding = models.JSONField(null=True, blank=True, editable=False)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	objects = UserManager()
	USERNAME_FIELD = "username"

	def save(self, *args, **kwargs):
		if self.is_superuser:
			self.role = "admin"
		super().save(*args, **kwargs)

	def __str__(self):
		return self.username


ACTION_CHOICES = (
	("CREATE", "Create"),
	("UPDATE", "Update"),
	("DELETE", "Delete"),
	("LOGIN", "Login"),
	("LOGOUT", "Logout"),
)


class AuditLog(models.Model):
	uuid = models.UUIDField(default=uuid4, editable=False, unique=True)

	user = models.ForeignKey(
		User,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="audit_logs",
	)

	action = models.CharField(
		max_length=20,
		choices=ACTION_CHOICES,
	)

	content_type = models.ForeignKey(
		ContentType,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
	)

	object_id = models.CharField(
		max_length=255,
		null=True,
		blank=True,
	)

	content_object = GenericForeignKey(
		"content_type",
		"object_id",
	)

	object_repr = models.CharField(
		max_length=500,
		blank=True,
	)

	changes = models.JSONField(
		default=dict,
		blank=True,
	)

	ip_address = models.GenericIPAddressField(
		null=True,
		blank=True,
	)

	user_agent = models.TextField(
		blank=True,
	)

	path = models.CharField(
		max_length=500,
		blank=True,
	)

	method = models.CharField(
		max_length=10,
		blank=True,
	)

	created_at = models.DateTimeField(
		auto_now_add=True,
		db_index=True,
	)

	def __str__(self):
		return f"{self.user} - {self.action} - {self.object_repr}"

	class Meta:
		ordering = ("-created_at",)
