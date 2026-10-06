from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group as AuthGroup
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import AuditLog, Faculty, Group, User

admin.site.unregister(AuthGroup)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
	form = UserChangeForm
	add_form = UserCreationForm
	change_password_form = AdminPasswordChangeForm

	list_display = ("username", "full_name", "role", "group", "faculty", "is_active")
	list_filter = ("role", "is_active", "faculty")
	search_fields = ("username", "full_name", "passport_pin")
	autocomplete_fields = ("group", "faculty")
	readonly_fields = ("uuid", "hemis_image_url", "last_login", "date_joined")
	fieldsets = (
		(None, {"fields": ("uuid", "username", "password", "role", "is_active")}),
		(
			"Shaxsiy ma'lumotlar",
			{
				"fields": (
					"full_name",
					"first_name",
					"second_name",
					"third_name",
					"short_name",
					"image",
					"hemis_image_url",
					"birth_date",
					"phone",
					"gender",
					"passport_pin",
					"passport_number",
				)
			},
		),
		("Ta'lim", {"fields": ("group", "faculty", "level", "semester", "gpa", "payment_form")}),
		("Manzil", {"fields": ("country", "province", "district", "address")}),
		("Ruxsatlar", {"fields": ("is_staff", "is_superuser", "user_permissions")}),
		("Vaqtlar", {"fields": ("last_login", "date_joined")}),
	)
	add_fieldsets = (
		(None, {"classes": ("wide",), "fields": ("username", "role", "password1", "password2")}),
	)


@admin.register(Group)
class GroupAdmin(ModelAdmin):
	list_display = ("name", "faculty", "teacher", "hemis_id")
	list_filter = ("faculty",)
	search_fields = ("name",)
	autocomplete_fields = ("teacher", "faculty")


@admin.register(Faculty)
class FacultyAdmin(ModelAdmin):
	list_display = ("name", "hemis_id")
	search_fields = ("name",)


@admin.register(AuditLog)
class AuditLogAdmin(ModelAdmin):
	list_display = ("created_at", "user", "action", "object_repr", "ip_address")
	list_filter = ("action",)
	search_fields = ("object_repr", "user__username")

	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return False
