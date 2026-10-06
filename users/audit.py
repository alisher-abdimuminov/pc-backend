"""
Audit jurnal: barcha amallar AuditLog'ga yoziladi.

- CREATE / UPDATE / DELETE - kuzatiladigan modellar uchun signal orqali avtomatik (o'zgargan maydonlar bilan)
- LOGIN / LOGOUT - auth view'larida log_action() orqali
So'rov konteksti (foydalanuvchi, IP, user-agent, yo'l, metod) AuditContextMiddleware orqali olinadi.
DRF JWT foydalanuvchini view ichida aniqlaydi va uni asl HttpRequest'ga ham yozadi - shuning uchun
signal paytida request.user to'g'ri bo'ladi.
"""

import contextvars
import datetime
import decimal
import logging
import uuid
from contextlib import contextmanager

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.signals import post_delete, post_save, pre_save

logger = logging.getLogger(__name__)

_request: contextvars.ContextVar = contextvars.ContextVar("audit_request", default=None)
_extra: contextvars.ContextVar = contextvars.ContextVar("audit_extra", default=None)

TRACKED_MODELS = (
	"users.User",
	"users.Group",
	"users.Faculty",
	"attendance.Location",
	"attendance.Schedule",
	"attendance.AttendanceAttempt",
	"assignments.Assignment",
	"assignments.Submission",
)
# o'zgarishlar ro'yxatiga kiritilmaydigan maydonlar
IGNORED_FIELDS = {"updated_at", "created_at", "last_login", "face_embedding", "date_joined", "id"}
# qiymati yashiriladigan maydonlar
SECRET_FIELDS = {"password", "passport_pin", "passport_number"}


class AuditContextMiddleware:
	def __init__(self, get_response):
		self.get_response = get_response

	def __call__(self, request):
		token = _request.set(request)
		try:
			return self.get_response(request)
		finally:
			_request.reset(token)


@contextmanager
def audit_extra(**data):
	"""Shu blok ichidagi keyingi log yozuvlariga qo'shimcha ma'lumot (masalan bloklash sababi)."""
	token = _extra.set({**(_extra.get() or {}), **data})
	try:
		yield
	finally:
		_extra.reset(token)


def _client_ip(request):
	forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
	return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


def _json(value):
	if value is None or isinstance(value, (bool, int, float, str)):
		return value
	if isinstance(value, (datetime.date, datetime.datetime, datetime.time)):
		return value.isoformat()
	if isinstance(value, (decimal.Decimal, uuid.UUID)):
		return str(value)
	if isinstance(value, models.Model):
		return str(value)
	if isinstance(value, models.fields.files.FieldFile):
		return value.name or None
	if isinstance(value, (list, tuple)):
		return [_json(v) for v in value]
	if isinstance(value, dict):
		return {k: _json(v) for k, v in value.items()}
	return str(value)


def log_action(action: str, obj=None, changes: dict | None = None, user=None):
	"""AuditLog yozuvi. Hech qachon asosiy amalni buzmaydi - xato bo'lsa faqat loglanadi."""
	from .models import AuditLog

	request = _request.get()
	if user is None and request is not None:
		candidate = getattr(request, "user", None)
		user = candidate if getattr(candidate, "is_authenticated", False) else None
	changes = {**(changes or {}), **(_extra.get() or {})}
	try:
		AuditLog.objects.create(
			user=user,
			action=action,
			content_type=ContentType.objects.get_for_model(obj) if obj is not None else None,
			object_id=str(obj.pk) if obj is not None else None,
			object_repr=(str(getattr(obj, "full_name", None) or obj) if obj is not None else "")[:500],
			changes=_json(changes),
			ip_address=_client_ip(request) if request else None,
			user_agent=request.META.get("HTTP_USER_AGENT", "") if request else "",
			path=request.path[:500] if request else "",
			method=request.method if request else "",
		)
	except Exception:  # noqa: BLE001
		logger.exception("AuditLog yozib bo'lmadi")


def _snapshot(instance) -> dict:
	data = {}
	for field in instance._meta.concrete_fields:
		if field.name in IGNORED_FIELDS:
			continue
		if field.is_relation:
			# FK - o'qiladigan ko'rinishda (masalan o'qituvchi F.I.Sh), id emas
			related = getattr(instance, field.name, None)
			value = str(getattr(related, "full_name", None) or related) if related is not None else None
		else:
			value = getattr(instance, field.attname)
			if isinstance(field, models.FileField):
				value = value.name if value else None
		data[field.name] = value
	return data


def _diff(old: dict, new: dict) -> dict:
	changes = {}
	for name, value in new.items():
		before = old.get(name)
		if before == value:
			continue
		if name in SECRET_FIELDS:
			changes[name] = ["***", "***"]
		else:
			changes[name] = [_json(before), _json(value)]
	return changes


def _pre_save(sender, instance, raw=False, **kwargs):
	if raw or instance._state.adding or not instance.pk:
		instance._audit_old = None
		return
	old = sender._default_manager.filter(pk=instance.pk).first()
	instance._audit_old = _snapshot(old) if old else None


def _post_save(sender, instance, created, raw=False, update_fields=None, **kwargs):
	if raw:
		return
	new = _snapshot(instance)
	if created:
		changes = {k: (["***", "***"] if k in SECRET_FIELDS else [None, _json(v)]) for k, v in new.items() if v not in (None, "")}
		log_action("CREATE", instance, changes)
		return
	changes = _diff(getattr(instance, "_audit_old", None) or {}, new)
	if changes:
		log_action("UPDATE", instance, changes)


def _post_delete(sender, instance, **kwargs):
	log_action("DELETE", instance, {"deleted": _json(_snapshot(instance))})


def connect_signals():
	for label in TRACKED_MODELS:
		model = apps.get_model(label)
		uid = f"audit-{label}"
		pre_save.connect(_pre_save, sender=model, dispatch_uid=f"{uid}-pre")
		post_save.connect(_post_save, sender=model, dispatch_uid=f"{uid}-post")
		post_delete.connect(_post_delete, sender=model, dispatch_uid=f"{uid}-delete")
