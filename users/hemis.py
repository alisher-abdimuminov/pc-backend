"""
HEMIS integratsiyasi: login -> token -> profil (me).
"""

import logging
from datetime import datetime
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.core.files.base import ContentFile

from .models import Faculty, Group, User

logger = logging.getLogger(__name__)

TIMEOUT = 15


class HemisError(Exception):
	pass


class HemisAuthError(HemisError):
	"""Login yoki parol noto'g'ri."""


def _url(key: str) -> str:
	return urljoin(settings.HEMIS["REST_API"], settings.HEMIS[key])


def _name(value):
	"""HEMIS ko'p maydonlarni {"code": ..., "name": ...} ko'rinishida qaytaradi."""
	if isinstance(value, dict):
		return value.get("name") or ""
	return value or ""


def _login(role: str, login: str, password: str) -> str:
	key = "STUDENT_LOGIN" if role == "student" else "TEACHER_LOGIN"
	# talaba logini son ko'rinishida (examples/hemis-student-login.md), tutor - string
	payload_login = int(login) if role == "student" and login.isdigit() else login
	try:
		response = requests.post(
			_url(key),
			json={"login": payload_login, "password": password},
			timeout=TIMEOUT,
		)
		print("resp:", response.url, response.text)
	except requests.RequestException as e:
		raise HemisError("HEMIS bilan bog'lanib bo'lmadi") from e

	if response.status_code in (400, 401, 403, 422):
		raise HemisAuthError("Login yoki parol noto'g'ri")
	if not response.ok:
		raise HemisError(f"HEMIS xatosi: {response.status_code}")

	body = response.json()
	token = (body.get("data") or {}).get("token")
	if not body.get("success", True) or not token:
		raise HemisAuthError("Login yoki parol noto'g'ri")
	return token


def _me(role: str, token: str) -> dict:
	key = "STUDENT_ME" if role == "student" else "TEACHER_ME"
	try:
		response = requests.get(
			_url(key),
			headers={"Authorization": f"Bearer {token}"},
			timeout=TIMEOUT,
		)
		response.raise_for_status()
	except requests.RequestException as e:
		raise HemisError("HEMIS profilini olib bo'lmadi") from e
	body = response.json()
	if role == "student":
		return body.get("data") or {}
	# tutor: {"result": {"user": {...}}} (examples/hemis-teacher-me.md)
	return (body.get("result") or {}).get("user") or {}


def _birth_date(value) -> str:
	if isinstance(value, (int, float)):
		return datetime.fromtimestamp(value).strftime("%Y-%m-%d")
	return value or ""


def _download_image(user: User, url: str):
	if not url.startswith("http") or (url == user.hemis_image_url and user.image):
		return
	try:
		response = requests.get(url, timeout=TIMEOUT)
		response.raise_for_status()
	except requests.RequestException:
		logger.warning("HEMIS rasmini yuklab bo'lmadi: %s", url)
		return
	user.image.save(f"{user.uuid}.jpg", ContentFile(response.content), save=False)
	user.hemis_image_url = url
	# etalon rasm o'zgardi - embedding qayta hisoblanadi
	user.face_embedding = None


def _sync_student(user: User, data: dict):
	faculty = None
	if faculty_data := data.get("faculty"):
		faculty, _ = Faculty.objects.update_or_create(
			hemis_id=faculty_data.get("id"),
			defaults={"name": faculty_data.get("name", "")},
		)
	group = None
	if group_data := data.get("group"):
		group, _ = Group.objects.update_or_create(
			hemis_id=group_data.get("id"),
			defaults={"name": group_data.get("name", ""), "faculty": faculty},
		)

	user.group = group
	user.faculty = faculty
	user.payment_form = _name(data.get("paymentForm"))
	user.level = _name(data.get("level"))
	user.semester = _name(data.get("semester"))
	try:
		user.gpa = float(data.get("avg_gpa"))
	except (TypeError, ValueError):
		user.gpa = None
	user.address = data.get("address") or ""
	user.country = _name(data.get("country"))
	user.province = _name(data.get("province"))
	user.district = _name(data.get("district"))


def _split_name(full_name: str) -> dict:
	"""'FAMILIYA ISM OTASINING ISMI' -> second/first/third/short name."""
	parts = (full_name or "").split()
	if len(parts) < 2:
		return {}
	second, first, third = parts[0], parts[1], " ".join(parts[2:])
	short = f"{second} {first[0]}." + (f" {third[0]}." if third else "")
	return {
		"second_name": second,
		"first_name": first,
		"third_name": third,
		"short_name": short,
	}


def _sync_teacher(user: User, data: dict):
	employee = data.get("employee") if isinstance(data.get("employee"), dict) else {}
	full_name = data.get("full_name") or employee.get("full_name") or ""
	names = _split_name(full_name)

	user.full_name = full_name
	user.first_name = employee.get("first_name") or names.get("first_name")
	user.second_name = employee.get("second_name") or names.get("second_name")
	user.third_name = employee.get("third_name") or names.get("third_name")
	user.short_name = employee.get("short_name") or names.get("short_name")
	user.phone = data.get("telephone") or user.phone
	if employee:
		user.birth_date = _birth_date(employee.get("birth_date")) or user.birth_date
		user.gender = _name(employee.get("gender")) or user.gender


def _sync_teacher_groups(user: User, data: dict):
	"""Tutorga biriktirilgan HEMIS guruhlari - Group.teacher shu user bo'ladi."""
	for item in data.get("groups") or []:
		if not isinstance(item, dict) or not item.get("id"):
			continue
		defaults = {"teacher": user}
		if item.get("name"):
			defaults["name"] = item["name"]
		Group.objects.update_or_create(hemis_id=item["id"], defaults=defaults)


def _sync_common(user: User, data: dict):
	user.first_name = data.get("first_name")
	user.second_name = data.get("second_name")
	user.third_name = data.get("third_name")
	user.full_name = data.get("full_name")
	user.short_name = data.get("short_name")
	user.birth_date = _birth_date(data.get("birth_date"))
	user.phone = data.get("phone")
	user.passport_pin = data.get("passport_pin")
	user.passport_number = data.get("passport_number")
	user.gender = _name(data.get("gender"))


def authenticate_hemis(login: str, password: str, roles=("student", "teacher")) -> User:
	"""
	HEMIS orqali tekshiradi (avval talaba, keyin o'qituvchi), userni yaratadi/yangilaydi
	va lokal parolni saqlaydi. Keyingi safar classic login ishlaydi.
	"""
	errors = []
	for role in roles:
		try:
			token = _login(role, login, password)
		except HemisError as e:
			errors.append(e)
			continue
		return _sync_user(role, login, password, token)
	# biror endpoint "parol xato" desa - shuni ko'rsatamiz, aks holda birinchi xatoni
	raise next((e for e in errors if isinstance(e, HemisAuthError)), errors[0])


def _sync_user(role: str, login: str, password: str, token: str) -> User:
	data = _me(role, token)

	user = User.objects.filter(username=login).first() or User(
		username=login, role=role
	)
	if role == "student":
		_sync_common(user, data)
		_sync_student(user, data)
	else:
		_sync_teacher(user, data)
	user.set_password(password)
	_download_image(user, str(data.get("image") or ""))
	user.save()
	if role == "teacher":
		_sync_teacher_groups(user, data)
	return user
