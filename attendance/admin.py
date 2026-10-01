from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import AutocompleteSelectFilter

from attendance.models import (
	Attendance,
	AttendanceAttempt,
	AttendanceStep,
	Location,
	Schedule,
)


@admin.register(Location)
class LocationModelAdmin(ModelAdmin):
	list_display = (
		"uuid",
		"name",
		"point_1",
		"point_2",
		"point_3",
		"point_4",
		"is_active",
	)
	search_fields = (
		"uuid",
		"name",
	)
	list_filter = ("is_active",)


@admin.register(Schedule)
class ScheduleModelAdmin(ModelAdmin):
	list_display = (
		"name",
		"location",
		"start_date",
		"end_date",
		"user",
		"group",
		"monday",
		"tuesday",
		"wednesday",
		"thursday",
		"friday",
		"saturday",
	)
	search_fields = ("uuid", "name")
	list_filter = (
		"location",
		"user",
		"group",
	)


@admin.register(Attendance)
class AttendanceModelAdmin(ModelAdmin):
	list_display = (
		"student",
		"schedule",
		"shift",
		"date",
	)
	search_fields = ("uuid",)
	list_filter = (
		["student", AutocompleteSelectFilter],
		["schedule", AutocompleteSelectFilter],
		"shift",
		"date",
	)


@admin.register(AttendanceStep)
class AttendanceStepModelAdmin(ModelAdmin):
	list_display = (
		"uuid",
		"step",
		"attendance",
		"success",
	)
	search_fields = ("uuid",)
	list_filter = (
		"step",
		["attendance", AutocompleteSelectFilter],
	)


@admin.register(AttendanceAttempt)
class AttendanceAttemptModelAdmin(ModelAdmin):
	list_display = (
		"uuid",
		"step",
		"ip_address",
		"location",
		"face_verified",
		"location_verified",
		"liveness_verified",
		"success",
	)
	search_fields = ("uuid", "ip_address")
	list_filter = (
		["step", AutocompleteSelectFilter],
		["location", AutocompleteSelectFilter],
		"face_verified",
		"location_verified",
		"liveness_verified",
	)
