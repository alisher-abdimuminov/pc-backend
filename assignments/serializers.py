from django.utils import timezone
from rest_framework import serializers

from users.models import Group

from .models import Assignment, Submission


class SubmissionSerializer(serializers.ModelSerializer):
	student = serializers.SerializerMethodField()
	graded_by = serializers.CharField(source="graded_by.full_name", default=None, read_only=True)

	class Meta:
		model = Submission
		fields = (
			"uuid",
			"student",
			"file",
			"submitted_at",
			"grade",
			"feedback",
			"graded_at",
			"graded_by",
		)
		read_only_fields = fields

	def get_student(self, obj):
		return {
			"uuid": obj.student.uuid,
			"full_name": obj.student.full_name or obj.student.username,
			"group": obj.student.group.name if obj.student.group else None,
		}


class AssignmentSerializer(serializers.ModelSerializer):
	teacher = serializers.CharField(source="teacher.full_name", read_only=True)
	groups = serializers.SerializerMethodField()
	group_uuids = serializers.SlugRelatedField(
		source="groups",
		slug_field="uuid",
		queryset=Group.objects.all(),
		many=True,
		write_only=True,
	)
	is_expired = serializers.SerializerMethodField()
	submissions_count = serializers.IntegerField(read_only=True, default=None)
	my_submission = serializers.SerializerMethodField()

	class Meta:
		model = Assignment
		fields = (
			"uuid",
			"teacher",
			"title",
			"description",
			"file",
			"deadline",
			"groups",
			"group_uuids",
			"is_expired",
			"submissions_count",
			"my_submission",
			"created_at",
			"updated_at",
		)
		read_only_fields = ("uuid", "created_at", "updated_at")

	def get_groups(self, obj):
		return [{"uuid": g.uuid, "name": g.name} for g in obj.groups.all()]

	def get_is_expired(self, obj):
		return obj.deadline < timezone.now()

	def get_my_submission(self, obj):
		submissions = getattr(obj, "my_submissions", None)
		if submissions is None:
			return None
		return SubmissionSerializer(submissions[0], context=self.context).data if submissions else None

	def validate_group_uuids(self, groups):
		allowed = self.context["allowed_groups"]
		if not groups:
			raise serializers.ValidationError("Kamida bitta guruh tanlang")
		if any(not allowed.filter(pk=g.pk).exists() for g in groups):
			raise serializers.ValidationError("Bu guruhga topshiriq bera olmaysiz")
		return groups


class SubmitSerializer(serializers.Serializer):
	file = serializers.FileField()


class GradeSerializer(serializers.Serializer):
	grade = serializers.FloatField(min_value=0, max_value=100)
	feedback = serializers.CharField(required=False, allow_blank=True, default="")
