from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Assignment, Submission


@admin.register(Assignment)
class AssignmentAdmin(ModelAdmin):
	list_display = ("title", "teacher", "deadline", "created_at")
	search_fields = ("title", "teacher__full_name")
	autocomplete_fields = ("teacher",)
	filter_horizontal = ("groups",)


@admin.register(Submission)
class SubmissionAdmin(ModelAdmin):
	list_display = ("assignment", "student", "submitted_at", "grade", "graded_at")
	search_fields = ("assignment__title", "student__full_name", "student__username")
	autocomplete_fields = ("assignment", "student", "graded_by")
