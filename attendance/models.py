from uuid import uuid4

from django.db import models

SHIFT = (
	(1, "1-SMENA"),
	(2, "2-SMENA"),
)

STEP = (
	(1, "1-qadam"),
	(2, "2-qadam"),
	(3, "3-qadam"),
)


class Location(models.Model):
	uuid = models.UUIDField(default=uuid4, editable=False, unique=True)
	name = models.CharField(max_length=255, unique=True)
	point_1 = models.CharField(max_length=100)
	point_2 = models.CharField(max_length=100)
	point_3 = models.CharField(max_length=100)
	point_4 = models.CharField(max_length=100)
	location = models.CharField(max_length=1000, null=True)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	@staticmethod
	def parse_point(value: str):
		try:
			lat, lng = value.split(",")

			lat = float(lat.strip())
			lng = float(lng.strip())

			if not -90 <= lat <= 90:
				raise ValueError("Latitude noto'g'ri")

			if not -180 <= lng <= 180:
				raise ValueError("Longitude noto'g'ri")

			return lat, lng

		except (ValueError, AttributeError):
			raise ValueError(
				"Koordinata 'latitude,longitude' formatida bo'lishi kerak. "
				"Masalan: 39.654321,66.987654"
			)

	def polygon(self):
		points = [
			self.parse_point(self.point_1),
			self.parse_point(self.point_2),
			self.parse_point(self.point_3),
			self.parse_point(self.point_4),
		]

		# parse_point -> (latitude, longitude)
		# Shapely -> (longitude, latitude)

		return [(lng, lat) for lat, lng in points]

	def __str__(self):
		return self.name.__str__()


class Schedule(models.Model):
	uuid = models.UUIDField(default=uuid4, editable=False, unique=True)
	name = models.CharField(max_length=100)
	start_date = models.DateField()
	end_date = models.DateField()

	user = models.ForeignKey(
		"users.User",
		on_delete=models.CASCADE,
		related_name="schedules",
		null=True,
		blank=True,
	)
	group = models.ForeignKey(
		"users.Group",
		on_delete=models.CASCADE,
		related_name="schedules",
		null=True,
		blank=True,
	)
	location = models.ForeignKey(
		"Location",
		on_delete=models.CASCADE,
		related_name="schedules",
	)

	monday = models.BooleanField(default=False)
	tuesday = models.BooleanField(default=False)
	wednesday = models.BooleanField(default=False)
	thursday = models.BooleanField(default=False)
	friday = models.BooleanField(default=False)
	saturday = models.BooleanField(default=False)

	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return self.name.__str__()


class Attendance(models.Model):
	uuid = models.UUIDField(default=uuid4, editable=False, unique=True)

	student = models.ForeignKey(
		"users.User", on_delete=models.CASCADE, related_name="attendances"
	)
	schedule = models.ForeignKey(
		Schedule,
		on_delete=models.PROTECT,
		null=True,
		blank=True,
		related_name="attendances",
	)

	shift = models.PositiveSmallIntegerField(choices=SHIFT)
	date = models.DateField()
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return self.uuid.__str__()

	class Meta:
		constraints = [
			models.UniqueConstraint(
				fields=["student", "schedule", "date"],
				name="uniq_student_schedule_date",
			)
		]


class AttendanceStep(models.Model):
	uuid = models.UUIDField(default=uuid4, editable=False, unique=True)
	step = models.PositiveSmallIntegerField(choices=STEP)
	attendance = models.ForeignKey(
		Attendance,
		on_delete=models.PROTECT,
		null=True,
		blank=True,
		related_name="steps",
	)
	success = models.BooleanField(default=False)

	def __str__(self):
		return self.uuid.__str__()

	class Meta:
		constraints = [
			models.UniqueConstraint(
				fields=["attendance", "step"], name="uniq_attendance_step"
			)
		]


class AttendanceAttempt(models.Model):
	uuid = models.UUIDField(default=uuid4, editable=False, unique=True)

	step = models.ForeignKey(
		AttendanceStep, on_delete=models.CASCADE, related_name="attempts"
	)
	image = models.ImageField(upload_to="attendance/%Y/%m/%d/")
	ip_address = models.GenericIPAddressField(null=True, blank=True)
	latitude = models.DecimalField(
		max_digits=18,
		decimal_places=15,
		null=True,
		blank=True,
	)

	longitude = models.DecimalField(
		max_digits=18,
		decimal_places=15,
		null=True,
		blank=True,
	)
	location = models.ForeignKey(
		Location,
		null=True,
		blank=True,
		on_delete=models.SET_NULL,
		related_name="attempts",
	)
	face_verified = models.BooleanField(default=False)
	location_verified = models.BooleanField(default=False)
	liveness_verified = models.BooleanField(default=False)
	success = models.BooleanField(default=False)
	error_code = models.CharField(max_length=100, blank=True)
	error_message = models.TextField(blank=True)
	face_distance = models.FloatField(null=True, blank=True)
	face_threshold = models.FloatField(null=True, blank=True)
	user_agent = models.TextField(blank=True)
	attempted_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return self.uuid.__str__()
