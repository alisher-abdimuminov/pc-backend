from uuid import uuid4

from django.db import models

from users.models import Group


class Assignment(models.Model):
	uuid = models.UUIDField(default=uuid4, editable=False, unique=True)
	teacher = models.ForeignKey(
		"users.User",
		on_delete=models.PROTECT,
		related_name="created_assignments",
	)
	title = models.CharField(max_length=255)
	description = models.TextField(blank=True)
	file = models.FileField(upload_to="assignments/%Y/%m/", null=True, blank=True)
	deadline = models.DateTimeField()
	groups = models.ManyToManyField(Group, related_name="assignments")
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return self.title


class Submission(models.Model):
	uuid = models.UUIDField(default=uuid4, editable=False, unique=True)
	assignment = models.ForeignKey(
		Assignment, on_delete=models.CASCADE, related_name="submissions"
	)
	student = models.ForeignKey(
		"users.User", on_delete=models.CASCADE, related_name="submissions"
	)
	file = models.FileField(upload_to="submissions/%Y/%m/")
	submitted_at = models.DateTimeField(auto_now=True)
	grade = models.FloatField(null=True, blank=True)
	feedback = models.TextField(blank=True)
	graded_at = models.DateTimeField(null=True, blank=True)
	graded_by = models.ForeignKey(
		"users.user",
		null=True,
		blank=True,
		on_delete=models.SET_NULL,
		related_name="graded_submissions",
	)

	class Meta:
		constraints = [
			models.UniqueConstraint(
				fields=["assignment", "student"],
				name="uniq_assignment_student_submission",
			)
		]
