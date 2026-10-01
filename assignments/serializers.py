from django.utils import timezone
from rest_framework import serializers

from users.models import Group

from .models import Assignment, Submission


class AssignmentGroupSerializer(serializers.ModelSerializer):
	class Meta:
		model = Group
		fields = (
			"uuid",
			"name",
		)


class AssignmentSerializer(serializers.ModelSerializer):
	teacher_name = serializers.CharField(
		source="teacher.full_name",
		read_only=True,
	)

	groups = serializers.SlugRelatedField(
		many=True,
		slug_field="uuid",
		queryset=Group.objects.all(),
	)

	groups_detail = AssignmentGroupSerializer(
		source="groups",
		many=True,
		read_only=True,
	)

	class Meta:
		model = Assignment
		fields = (
			"uuid",
			"teacher",
			"teacher_name",
			"title",
			"description",
			"file",
			"deadline",
			"groups",
			"groups_detail",
			"created_at",
			"updated_at",
		)

		read_only_fields = (
			"teacher",
			"created_at",
			"updated_at",
		)

	def validate_groups(self, groups):
		request = self.context.get("request")

		if not request:
			return groups

		for group in groups:
			if group.teacher_id != request.user.id:
				raise serializers.ValidationError(
					"Faqat o'zingizga biriktirilgan guruhlarni tanlashingiz mumkin."
				)

		return groups


class SubmissionSerializer(serializers.ModelSerializer):
	student_uuid = serializers.UUIDField(
		source="student.uuid",
		read_only=True,
	)

	student_name = serializers.CharField(
		source="student.full_name",
		read_only=True,
	)

	student_username = serializers.CharField(
		source="student.username",
		read_only=True,
	)

	assignment_uuid = serializers.UUIDField(
		source="assignment.uuid",
		read_only=True,
	)

	assignment_title = serializers.CharField(
		source="assignment.title",
		read_only=True,
	)

	graded_by_name = serializers.CharField(
		source="graded_by.full_name",
		read_only=True,
		allow_null=True,
	)

	class Meta:
		model = Submission
		fields = (
			"uuid",
			"assignment_uuid",
			"assignment_title",
			"student_uuid",
			"student_name",
			"student_username",
			"file",
			"submitted_at",
			"grade",
			"feedback",
			"graded_at",
			"graded_by_name",
		)


class GradeSubmissionSerializer(serializers.Serializer):
	grade = serializers.FloatField()

	feedback = serializers.CharField(
		required=False,
		allow_blank=True,
	)


class StudentSubmissionSerializer(serializers.ModelSerializer):
	assignment = serializers.SlugRelatedField(
		slug_field="uuid",
		queryset=Assignment.objects.all(),
	)

	class Meta:
		model = Submission
		fields = (
			"uuid",
			"assignment",
			"file",
			"submitted_at",
			"grade",
			"feedback",
			"graded_at",
		)

		read_only_fields = (
			"uuid",
			"submitted_at",
			"grade",
			"feedback",
			"graded_at",
		)

	def validate_assignment(self, assignment):
		request = self.context["request"]
		student = request.user

		if not student.group_id:
			raise serializers.ValidationError("Talaba guruhga biriktirilmagan.")

		if not assignment.groups.filter(
			pk=student.group_id,
		).exists():
			raise serializers.ValidationError(
				"Bu topshiriq sizning guruhingiz uchun emas."
			)

		if assignment.deadline < timezone.now():
			raise serializers.ValidationError("Topshiriq muddati tugagan.")

		if not self.instance:
			if Submission.objects.filter(
				assignment=assignment,
				student=student,
			).exists():
				raise serializers.ValidationError(
					"Bu topshiriq uchun fayl allaqachon yuborilgan."
				)

		return assignment

	def validate(self, attrs):
		if self.instance:
			if self.instance.graded_at is not None or self.instance.grade is not None:
				raise serializers.ValidationError(
					"Baholangan topshiriqni o'zgartirish mumkin emas."
				)

			if self.instance.assignment.deadline < timezone.now():
				raise serializers.ValidationError("Topshiriq muddati tugagan.")

		return attrs

	def create(self, validated_data):
		validated_data["student"] = self.context["request"].user

		return super().create(validated_data)


class StudentAssignmentSubmissionSerializer(serializers.ModelSerializer):
	class Meta:
		model = Submission
		fields = (
			"uuid",
			"file",
			"submitted_at",
			"grade",
			"feedback",
			"graded_at",
		)


class StudentAssignmentSerializer(serializers.ModelSerializer):
	teacher_name = serializers.CharField(
		source="teacher.full_name",
		read_only=True,
	)

	submission = serializers.SerializerMethodField()
	available = serializers.SerializerMethodField()

	class Meta:
		model = Assignment
		fields = (
			"uuid",
			"teacher_name",
			"title",
			"description",
			"file",
			"deadline",
			"created_at",
			"submission",
			"available",
		)

	def get_submission(self, obj):
		submissions = getattr(
			obj,
			"student_submissions",
			[],
		)

		if not submissions:
			return None

		return StudentAssignmentSubmissionSerializer(
			submissions[0],
			context=self.context,
		).data

	def get_available(self, obj):
		if obj.deadline < timezone.now():
			return False

		submissions = getattr(
			obj,
			"student_submissions",
			[],
		)

		if not submissions:
			return True

		submission = submissions[0]

		return submission.graded_at is None and submission.grade is None
