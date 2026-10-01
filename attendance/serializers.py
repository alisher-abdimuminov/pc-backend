from rest_framework import serializers

from users.models import Group, User
from users.serializers import GroupSerializer, UserSerializer

from .models import AttendanceAttempt, AttendanceStep, Location, Schedule


class LocationSerializer(serializers.ModelSerializer):
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
			"is_active",
			"created_at",
			"updated_at",
		)


class ScheduleSerializer(serializers.ModelSerializer):
	user = serializers.SlugRelatedField(
		slug_field="uuid",
		queryset=User.objects.all(),
		required=False,
		allow_null=True,
	)

	group = serializers.SlugRelatedField(
		slug_field="uuid",
		queryset=Group.objects.all(),
		required=False,
		allow_null=True,
	)

	location = serializers.SlugRelatedField(
		slug_field="uuid",
		queryset=Location.objects.all(),
	)

	class Meta:
		model = Schedule
		fields = (
			"uuid",
			"name",
			"start_date",
			"end_date",
			"user",
			"group",
			"location",
			"monday",
			"tuesday",
			"wednesday",
			"thursday",
			"friday",
			"saturday",
			"is_active",
		)

	def to_representation(self, instance):
		response = super().to_representation(instance)

		response["user"] = UserSerializer(instance.user).data if instance.user else None

		response["group"] = (
			GroupSerializer(instance.group).data if instance.group else None
		)

		response["location"] = (
			LocationSerializer(instance.location).data if instance.location else None
		)

		return response


class AttendanceDaySerializer(serializers.Serializer):
	date = serializers.DateField()

	step_1 = serializers.BooleanField()
	step_2 = serializers.BooleanField()
	step_3 = serializers.BooleanField()


class AttendanceStudentSerializer(serializers.Serializer):
	uuid = serializers.UUIDField()
	full_name = serializers.CharField()

	days = AttendanceDaySerializer(
		many=True,
	)


class AttendanceMonitoringSerializer(serializers.Serializer):
	group_uuid = serializers.UUIDField()
	group_name = serializers.CharField()

	start_date = serializers.DateField()
	end_date = serializers.DateField()

	dates = serializers.ListField(
		child=serializers.DateField(),
	)

	students = AttendanceStudentSerializer(
		many=True,
	)


class AttendanceAttemptSerializer(serializers.ModelSerializer):
	student_uuid = serializers.SerializerMethodField()
	student_name = serializers.SerializerMethodField()
	student_username = serializers.SerializerMethodField()

	attendance_date = serializers.SerializerMethodField()
	schedule_name = serializers.SerializerMethodField()

	step_number = serializers.IntegerField(
		source="step.step",
		read_only=True,
	)

	location_name = serializers.CharField(
		source="location.name",
		read_only=True,
		allow_null=True,
	)

	class Meta:
		model = AttendanceAttempt
		fields = (
			"uuid",
			"student_uuid",
			"student_name",
			"student_username",
			"attendance_date",
			"schedule_name",
			"step_number",
			"image",
			"ip_address",
			"latitude",
			"longitude",
			"location_name",
			"face_verified",
			"location_verified",
			"liveness_verified",
			"success",
			"error_code",
			"error_message",
			"face_distance",
			"face_threshold",
			"user_agent",
			"attempted_at",
		)

	def get_attendance(self, obj):
		return obj.step.attendance if obj.step else None

	def get_student_uuid(self, obj):
		attendance = self.get_attendance(obj)

		if not attendance:
			return None

		return attendance.student.uuid

	def get_student_name(self, obj):
		attendance = self.get_attendance(obj)

		if not attendance:
			return None

		return attendance.student.full_name

	def get_student_username(self, obj):
		attendance = self.get_attendance(obj)

		if not attendance:
			return None

		return attendance.student.username

	def get_attendance_date(self, obj):
		attendance = self.get_attendance(obj)

		if not attendance:
			return None

		return attendance.date

	def get_schedule_name(self, obj):
		attendance = self.get_attendance(obj)

		if not attendance or not attendance.schedule:
			return None

		return attendance.schedule.name


class AttendanceCheckSerializer(serializers.Serializer):
	face_image = serializers.ImageField()

	latitude = serializers.DecimalField(
		max_digits=18,
		decimal_places=15,
	)

	longitude = serializers.DecimalField(
		max_digits=18,
		decimal_places=15,
	)


class AttendanceStepSerializer(serializers.ModelSerializer):
	class Meta:
		model = AttendanceStep
		fields = (
			"uuid",
			"step",
			"success",
		)


# class AttendanceAttemptSerializer(
# 	serializers.ModelSerializer
# ):
# 	student_uuid = (
# 		serializers.UUIDField(
# 			source=(
# 				"step.attendance."
# 				"student.uuid"
# 			),
# 			read_only=True,
# 		)
# 	)
#
# 	student_name = (
# 		serializers.CharField(
# 			source=(
# 				"step.attendance."
# 				"student.full_name"
# 			),
# 			read_only=True,
# 		)
# 	)
#
# 	student_username = (
# 		serializers.CharField(
# 			source=(
# 				"step.attendance."
# 				"student.username"
# 			),
# 			read_only=True,
# 		)
# 	)
#
# 	attendance_date = (
# 		serializers.DateField(
# 			source=(
# 				"step.attendance.date"
# 			),
# 			read_only=True,
# 		)
# 	)
#
# 	schedule_name = (
# 		serializers.CharField(
# 			source=(
# 				"step.attendance."
# 				"schedule.name"
# 			),
# 			read_only=True,
# 			allow_null=True,
# 		)
# 	)
#
# 	step_number = (
# 		serializers.IntegerField(
# 			source="step.step",
# 			read_only=True,
# 		)
# 	)
#
# 	location_name = (
# 		serializers.CharField(
# 			source="location.name",
# 			read_only=True,
# 			allow_null=True,
# 		)
# 	)
#
# 	class Meta:
# 		model = AttendanceAttempt
#
# 		fields = (
# 			"uuid",
#
# 			"student_uuid",
# 			"student_name",
# 			"student_username",
#
# 			"attendance_date",
# 			"schedule_name",
# 			"step_number",
#
# 			"image",
#
# 			"ip_address",
# 			"latitude",
# 			"longitude",
#
# 			"location_name",
#
# 			"face_verified",
# 			"location_verified",
# 			"liveness_verified",
#
# 			"success",
#
# 			"error_code",
# 			"error_message",
#
# 			"face_distance",
# 			"face_threshold",
#
# 			"user_agent",
# 			"attempted_at",
# 		)
