from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import (
	AutocompleteSelectFilter,
)

from .models import Faculty, Group, User


@admin.register(Group)
class GroupModelAdmin(ModelAdmin):
	list_display = ("uuid", "name", "created_at")
	search_fields = ("name",)


@admin.register(Faculty)
class FacultyModelAdmin(ModelAdmin):
	list_display = ("uuid", "name", "created_at")
	search_fields = ("name",)


@admin.register(User)
class UserModelAdmin(UserAdmin, ModelAdmin):
	add_form = UserCreationForm
	form = UserChangeForm
	list_display = (
		"uuid",
		"username",
		"full_name",
		"phone",
		"faculty__name",
		"group__name",
	)
	search_fields = (
		"username",
		"full_name",
	)
	list_filter = (
		["group", AutocompleteSelectFilter],
		["faculty", AutocompleteSelectFilter],
		"role",
	)

	list_filter_submit = True
	autocomplete_fields = (
		"group",
		"faculty",
	)
	model = User

	fieldsets = (
		(
			"Ma'lumotlar",
			{
				"fields": (
					"username",
					# 1
					"first_name",
					"second_name",
					"third_name",
					"full_name",
					"short_name",
					# 2
					"image",
					"birth_date",
					"email",
					"phone",
					"passport_pin",
					"passport_number",
					"gender",
					"payment_form",
					# 3
					"group",
					"faculty",
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
					"is_active",
				),
			},
		),
	)

	add_fieldsets = (
		(
			"Ma'lumotlar",
			{
				"fields": (
					"username",
					"password1",
					"password2",
					"full_name",
					"role",
				),
			},
		),
	)
