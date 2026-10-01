from rest_framework import serializers

from .models import Faculty, Group, User


class UserSerializer(serializers.ModelSerializer):
	faculty_name = serializers.CharField(source="faculty.name", read_only=True)
	group_name = serializers.CharField(source="group.name", read_only=True)
	image_url = serializers.SerializerMethodField()

	class Meta:
		model = User
		fields = (
			"uuid",
			"username",
			# 1
			"first_name",
			"second_name",
			"third_name",
			"full_name",
			"short_name",
			# 2
			"image",
			"image_url",
			"birth_date",
			"email",
			"phone",
			"passport_pin",
			"passport_number",
			"gender",
			"payment_form",
			# 3
			"group",
			"group_name",
			"faculty",
			"faculty_name",
			"level",
			"semester",
			"gpa",
			# 4
			"address",
			"country",
			"province",
			"district",
			# 5
			"role",
			"created_at",
			"is_active",
		)
		read_only_fields = ("image_url",)

	def get_image_url(self, obj):
		if not obj.image:
			return None
		req = self.context.get("request")
		return req.build_absolute_uri(obj.image.url) if req else obj.image.url


class GroupSerializer(serializers.ModelSerializer):
	teacher = serializers.SlugRelatedField(
		slug_field="uuid",
		queryset=User.objects.filter(
			role="teacher",
		),
		required=False,
		allow_null=True,
	)
	teacher_name = serializers.CharField(source="teacher.full_name", read_only=True)
	student_count = serializers.IntegerField(source="students.count", read_only=True)

	class Meta:
		model = Group
		fields = (
			"uuid",
			"name",
			"hemis_id",
			"teacher",
			"teacher_name",
			"student_count",
			"created_at",
		)

	def validate_teacher(self, v):
		if v and v.role != "teacher":
			raise serializers.ValidationError("Faqat teacher biriktiriladi")
		return v


class FacultySerializer(serializers.ModelSerializer):
	student_count = serializers.IntegerField(source="students.count", read_only=True)

	class Meta:
		model = Faculty
		fields = (
			"uuid",
			"name",
			"hemis_id",
			"student_count",
			"created_at",
		)
