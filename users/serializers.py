from rest_framework import serializers

from .models import AuditLog, Faculty, Group, User
from .permissions import PERMISSION_CODES, effective_permissions


class FacultySerializer(serializers.ModelSerializer):
	class Meta:
		model = Faculty
		fields = ("uuid", "name")


class GroupSerializer(serializers.ModelSerializer):
	class Meta:
		model = Group
		fields = ("uuid", "name")


class UserSerializer(serializers.ModelSerializer):
	group = GroupSerializer(read_only=True)
	faculty = FacultySerializer(read_only=True)
	# frontend menyu va sahifalarni shu ro'yxat bo'yicha ko'rsatadi (backend ham xuddi shu qoidani tekshiradi)
	permissions = serializers.SerializerMethodField()

	def get_permissions(self, obj):
		return sorted(effective_permissions(obj))

	class Meta:
		model = User
		fields = (
			"uuid",
			"username",
			"role",
			"full_name",
			"short_name",
			"first_name",
			"second_name",
			"third_name",
			"image",
			"phone",
			"gender",
			"group",
			"faculty",
			"level",
			"semester",
			"permissions",
		)


class StaffSerializer(serializers.ModelSerializer):
	"""little roli xodimi (admin boshqaradi)."""

	password = serializers.CharField(write_only=True, required=False, min_length=6)
	permissions = serializers.ListField(child=serializers.CharField(), required=False)

	class Meta:
		model = User
		fields = ("uuid", "username", "full_name", "is_active", "password", "permissions", "last_login", "created_at")
		read_only_fields = ("uuid", "last_login", "created_at")
		extra_kwargs = {"full_name": {"required": True, "allow_blank": False}}

	def to_representation(self, instance):
		data = super().to_representation(instance)
		data["permissions"] = sorted(
			f"{p.content_type.app_label}.{p.codename}"
			for p in instance.user_permissions.all()
			if f"{p.content_type.app_label}.{p.codename}" in PERMISSION_CODES
		)
		return data

	def validate_username(self, value):
		if self.instance is not None and value != self.instance.username:
			raise serializers.ValidationError("Loginni o'zgartirib bo'lmaydi")
		if self.instance is None and User.objects.filter(username=value).exists():
			raise serializers.ValidationError("Bu login band")
		return value

	def validate(self, attrs):
		if self.instance is None and not attrs.get("password"):
			raise serializers.ValidationError({"password": "Parol kiriting"})
		return attrs

	def create(self, validated_data):
		validated_data.pop("permissions", None)
		password = validated_data.pop("password")
		return User.objects.create_user(role="little", password=password, **validated_data)

	def update(self, instance, validated_data):
		validated_data.pop("permissions", None)
		validated_data.pop("username", None)
		if password := validated_data.pop("password", None):
			instance.set_password(password)
		for key, value in validated_data.items():
			setattr(instance, key, value)
		instance.save()
		return instance


class AuditLogSerializer(serializers.ModelSerializer):
	user = serializers.SerializerMethodField()
	model = serializers.SerializerMethodField()
	action_display = serializers.CharField(source="get_action_display")

	class Meta:
		model = AuditLog
		fields = (
			"uuid",
			"created_at",
			"action",
			"action_display",
			"user",
			"model",
			"object_id",
			"object_repr",
			"changes",
			"ip_address",
			"user_agent",
			"path",
			"method",
		)

	def get_user(self, obj):
		if not obj.user:
			return None
		return {
			"uuid": obj.user.uuid,
			"full_name": obj.user.full_name or obj.user.username,
			"username": obj.user.username,
			"role": obj.user.role,
		}

	def get_model(self, obj):
		if not obj.content_type:
			return None
		model = obj.content_type.model_class()
		return {
			"value": f"{obj.content_type.app_label}.{obj.content_type.model}",
			"label": str(model._meta.verbose_name) if model else obj.content_type.model,
		}


class LoginSerializer(serializers.Serializer):
	login = serializers.CharField()
	password = serializers.CharField()
