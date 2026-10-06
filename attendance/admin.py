from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import Attendance, AttendanceAttempt, AttendanceStep, Location, Schedule


@admin.register(Location)
class LocationAdmin(ModelAdmin):
	list_display = ("name", "location", "is_active", "created_at")
	list_filter = ("is_active",)
	search_fields = ("name", "location")


@admin.register(Schedule)
class ScheduleAdmin(ModelAdmin):
	list_display = ("name", "group", "user", "location", "start_date", "end_date", "is_active")
	list_filter = ("is_active", "location")
	search_fields = ("name", "group__name", "user__full_name", "user__username")
	autocomplete_fields = ("group", "user", "location")


class AttendanceStepInline(TabularInline):
	model = AttendanceStep
	extra = 0
	fields = ("step", "success")


@admin.register(Attendance)
class AttendanceAdmin(ModelAdmin):
	list_display = ("student", "date", "shift", "schedule", "created_at")
	list_filter = ("shift", "date")
	search_fields = ("student__full_name", "student__username")
	autocomplete_fields = ("student", "schedule")
	date_hierarchy = "date"
	inlines = (AttendanceStepInline,)


@admin.register(AttendanceAttempt)
class AttendanceAttemptAdmin(ModelAdmin):
	list_display = (
		"attempted_at",
		"step",
		"success",
		"face_verified",
		"location_verified",
		"liveness_verified",
		"error_code",
		"face_distance",
	)
	list_filter = ("success", "face_verified", "location_verified", "error_code")
	search_fields = ("step__attendance__student__full_name", "step__attendance__student__username")
	readonly_fields = [f.name for f in AttendanceAttempt._meta.fields]

	def has_add_permission(self, request):
		return False
