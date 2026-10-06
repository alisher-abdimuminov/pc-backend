from rest_framework import serializers

from users.models import Group, User

from .models import Attendance, AttendanceAttempt, AttendanceStep, Location, Schedule
from .services import schedule_weekdays


class LocationSerializer(serializers.ModelSerializer):
	polygon = serializers.SerializerMethodField()

	class Meta:
		model = Location
		fields = (
			"uuid",
			"name",
			"point_1",
			"point_2",
			"point_3",
			"point_4",
			"location",
			"polygon",
			"is_active",
			"created_at",
		)
		read_only_fields = ("uuid", "created_at")

	def get_polygon(self, obj):
		"""Frontend xaritasi uchun [[lat, lng], ...]"""
		try:
			return [[lat, lng] for lng, lat in obj.polygon()]
		except ValueError:
			return []

	def validate(self, attrs):
		for key in ("point_1", "point_2", "point_3", "point_4"):
			if key in attrs:
				try:
					lat, lng = Location.parse_point(attrs[key])
				except ValueError as e:
					raise serializers.ValidationError({key: str(e)}) from e
				attrs[key] = f"{lat},{lng}"
		return attrs


class LocationShortSerializer(LocationSerializer):
	class Meta(LocationSerializer.Meta):
		fields = ("uuid", "name", "location", "polygon")


class ScheduleSerializer(serializers.ModelSerializer):
	location = LocationShortSerializer(read_only=True)
	location_uuid = serializers.SlugRelatedField(
		source="location", slug_field="uuid", queryset=Location.objects.all(), write_only=True
	)
	group = serializers.SerializerMethodField()
	user = serializers.SerializerMethodField()
	group_uuid = serializers.SlugRelatedField(
		source="group",
		slug_field="uuid",
		queryset=Group.objects.all(),
		write_only=True,
		required=False,
		allow_null=True,
	)
	user_uuid = serializers.SlugRelatedField(
		source="user",
		slug_field="uuid",
		queryset=User.objects.filter(role="student"),
		write_only=True,
		required=False,
		allow_null=True,
	)
	weekdays = serializers.SerializerMethodField()

	class Meta:
		model = Schedule
		fields = (
			"uuid",
			"name",
			"start_date",
			"end_date",
			"group",
			"group_uuid",
			"user",
			"user_uuid",
			"location",
			"location_uuid",
			"monday",
			"tuesday",
			"wednesday",
			"thursday",
			"friday",
			"saturday",
			"weekdays",
			"is_active",
			"created_at",
		)
		read_only_fields = ("uuid", "created_at")

	def get_group(self, obj):
		return {"uuid": obj.group.uuid, "name": obj.group.name} if obj.group else None

	def get_user(self, obj):
		return {"uuid": obj.user.uuid, "full_name": obj.user.full_name} if obj.user else None

	def get_weekdays(self, obj):
		return schedule_weekdays(obj)

	def validate(self, attrs):
		group = attrs.get("group", getattr(self.instance, "group", None))
		user = attrs.get("user", getattr(self.instance, "user", None))
		if not group and not user:
			raise serializers.ValidationError("Guruh yoki talaba tanlanishi kerak")
		start = attrs.get("start_date", getattr(self.instance, "start_date", None))
		end = attrs.get("end_date", getattr(self.instance, "end_date", None))
		if start and end and start > end:
			raise serializers.ValidationError({"end_date": "Tugash sanasi boshlanishdan oldin bo'lmasin"})
		return attrs


class StepStateSerializer(serializers.Serializer):
	step = serializers.IntegerField()
	start = serializers.TimeField(format="%H:%M")
	end = serializers.TimeField(format="%H:%M")
	status = serializers.CharField()


class DayStateSerializer(serializers.Serializer):
	date = serializers.DateField()
	now = serializers.DateTimeField()
	schedule = ScheduleSerializer()
	shift = serializers.IntegerField()
	shift_locked = serializers.BooleanField()
	current_step = serializers.IntegerField()
	can_attempt = serializers.BooleanField()
	message = serializers.CharField()
	steps = StepStateSerializer(many=True)


class AttemptSerializer(serializers.ModelSerializer):
	step = serializers.IntegerField(source="step.step")

	class Meta:
		model = AttendanceAttempt
		fields = (
			"uuid",
			"step",
			"image",
			"latitude",
			"longitude",
			"face_verified",
			"location_verified",
			"liveness_verified",
			"success",
			"error_code",
			"error_message",
			"face_distance",
			"face_threshold",
			"ip_address",
			"attempted_at",
		)


class StudentAttemptSerializer(serializers.ModelSerializer):
	"""Talabaga qaytariladigan natija: rasm, koordinata, yuz masofasi va IP berilmaydi."""

	step = serializers.IntegerField(source="step.step")

	class Meta:
		model = AttendanceAttempt
		fields = (
			"uuid",
			"step",
			"success",
			"error_code",
			"error_message",
			"location_verified",
			"face_verified",
			"attempted_at",
		)


class AttemptListSerializer(AttemptSerializer):
	"""Urinishlar ro'yxati uchun: talaba, guruh, joy, smena bilan."""

	student = serializers.SerializerMethodField()
	group = serializers.CharField(source="step.attendance.student.group.name", default=None)
	location_name = serializers.CharField(source="location.name", default=None)
	shift = serializers.IntegerField(source="step.attendance.shift")
	date = serializers.DateField(source="step.attendance.date")

	class Meta(AttemptSerializer.Meta):
		fields = (*AttemptSerializer.Meta.fields, "student", "group", "location_name", "shift", "date")

	def get_student(self, obj):
		student = obj.step.attendance.student
		request = self.context.get("request")
		image = student.image.url if student.image else None
		return {
			"uuid": student.uuid,
			"full_name": student.full_name or student.username,
			"username": student.username,
			"image": request.build_absolute_uri(image) if request and image else image,
			"is_active": student.is_active,
		}


class AttendanceStepSerializer(serializers.ModelSerializer):
	attempts = AttemptSerializer(many=True, read_only=True)

	class Meta:
		model = AttendanceStep
		fields = ("uuid", "step", "success", "attempts")


class AttendanceSerializer(serializers.ModelSerializer):
	location = serializers.CharField(source="schedule.location.name", default=None)
	passed_steps = serializers.SerializerMethodField()

	class Meta:
		model = Attendance
		fields = ("uuid", "date", "shift", "location", "passed_steps", "created_at")

	def get_passed_steps(self, obj):
		return sorted(s.step for s in obj.steps.all() if s.success)


class StepSummarySerializer(serializers.ModelSerializer):
	class Meta:
		model = AttendanceStep
		fields = ("uuid", "step", "success")


class AttendanceSummarySerializer(AttendanceSerializer):
	"""Urinishlarsiz: faqat qaysi qadam tasdiqlangan ("keldi/kelmadi")."""

	steps = StepSummarySerializer(many=True, read_only=True)

	class Meta(AttendanceSerializer.Meta):
		fields = (*AttendanceSerializer.Meta.fields, "steps")


class AttendanceDetailSerializer(AttendanceSerializer):
	steps = AttendanceStepSerializer(many=True, read_only=True)

	class Meta(AttendanceSerializer.Meta):
		fields = (*AttendanceSerializer.Meta.fields, "steps")


class LocationCheckSerializer(serializers.Serializer):
	latitude = serializers.FloatField(min_value=-90, max_value=90)
	longitude = serializers.FloatField(min_value=-180, max_value=180)
	# GPS aniqligi majburiy - aniqligi noma'lum koordinata qabul qilinmaydi
	accuracy = serializers.FloatField(min_value=0)


class CheckInSerializer(LocationCheckSerializer):
	image = serializers.ImageField()
	location_token = serializers.CharField()
