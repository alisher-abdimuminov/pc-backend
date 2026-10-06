"""
FaceID - to'liq backendda, deepface bilan.

Frontend faqat sifatli rasm olishni ta'minlaydi (pre-FaceID). Tasdiqlash shu yerda:
	1. DeepFace.extract_faces(joriy_rasm, anti_spoofing=True) - yuz bormi, jonli yuzmi (spoof emasmi),
	   bitta yuzmi, aniq va yetarli kattami
	2. DeepFace.verify(talaba_rasmi, joriy_rasm) - talabaning HEMIS rasmi (user.image) bilan
	   hozir olingan rasm bir odammi (ArcFace, cosine masofa <= model chegarasi)

deepface/tensorflow og'ir bo'lgani uchun lazy import qilinadi.
"""

import logging
from dataclasses import dataclass

import numpy as np
from django.conf import settings
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

# joriy rasm (selfie) talablari
MIN_FACE_CONFIDENCE = 0.9
# yuz kengligi kadr kengligining kamida shuncha qismi bo'lishi kerak
MIN_FACE_WIDTH_RATIO = 0.15
# asosiy yuzning shuncha qismidan katta boshqa yuz ham bo'lsa - "bir nechta yuz"
OTHER_FACE_AREA_RATIO = 0.25


class NoReferenceImage(Exception):
	"""Talabaning profil rasmi yo'q yoki unda yuz topilmadi."""


@dataclass
class FaceResult:
	# success | no_face | multiple_faces | face_small | spoof | face | no_reference
	result: str
	distance: float | None = None
	threshold: float | None = None
	# anti-spoofing'dan o'tdimi (jonli yuz)
	liveness: bool = False


def _config(key):
	return settings.ATTENDANCE[key]


def load_image(file) -> np.ndarray:
	"""Faylni deepface kutadigan BGR numpy massivga aylantiradi."""
	image = ImageOps.exif_transpose(Image.open(file)).convert("RGB")
	image.thumbnail((1280, 1280))
	return np.array(image)[:, :, ::-1].copy()


def load_reference(user) -> np.ndarray:
	"""Talabaning etalon rasmi - HEMIS'dan olingan profil rasmi."""
	if not user.image:
		raise NoReferenceImage
	with user.image.open("rb") as f:
		return load_image(f)


def _area(face: dict) -> int:
	return face["facial_area"]["w"] * face["facial_area"]["h"]


def selfie_problem(faces: list[dict], image_width: int) -> str:
	"""
	extract_faces natijasi bo'yicha joriy rasm talablari. Muammo bo'lsa xato kodini, aks holda bo'sh satr.
	faces - kattadan kichikka saralangan.
	"""
	main = faces[0]
	if any(_area(f) >= _area(main) * OTHER_FACE_AREA_RATIO for f in faces[1:]):
		return "multiple_faces"
	if (main.get("confidence") or 0) < MIN_FACE_CONFIDENCE:
		return "no_face"
	if main["facial_area"]["w"] < image_width * MIN_FACE_WIDTH_RATIO:
		return "face_small"
	return ""


def verify(user, img: np.ndarray) -> FaceResult:
	"""Joriy rasmni (img) talabaning profil rasmi bilan solishtiradi."""
	from deepface import DeepFace
	from deepface.modules.exceptions import FaceNotDetected

	detector = _config("FACE_DETECTOR")
	anti_spoofing = _config("FACE_ANTI_SPOOFING")

	# 1. joriy rasm: yuz + anti-spoofing + sifat
	try:
		faces = DeepFace.extract_faces(
			img_path=img,
			detector_backend=detector,
			enforce_detection=True,
			align=True,
			anti_spoofing=anti_spoofing,
		)
	except FaceNotDetected:
		return FaceResult("no_face")
	faces.sort(key=_area, reverse=True)

	if anti_spoofing and not faces[0].get("is_real", False):
		logger.info("face spoof user=%s score=%s", user.pk, faces[0].get("antispoof_score"))
		return FaceResult("spoof")
	if problem := selfie_problem(faces, image_width=img.shape[1]):
		return FaceResult(problem, liveness=anti_spoofing)

	# 2. talaba rasmi bilan solishtirish
	reference = load_reference(user)
	try:
		result = DeepFace.verify(
			img1_path=reference,
			img2_path=img,
			model_name=_config("FACE_MODEL"),
			detector_backend=detector,
			distance_metric=_config("FACE_DISTANCE_METRIC"),
			enforce_detection=True,
			align=True,
			# joriy rasm 1-bosqichda tekshirilgan
			anti_spoofing=False,
		)
	except ValueError as e:
		# deepface: "Exception while processing img1_path" - profil rasmida yuz yo'q
		if "img1" in str(e):
			raise NoReferenceImage from e
		return FaceResult("no_face", liveness=anti_spoofing)

	logger.info(
		"face verify user=%s verified=%s distance=%.4f threshold=%.4f",
		user.pk,
		result["verified"],
		result["distance"],
		result["threshold"],
	)
	return FaceResult(
		"success" if result["verified"] else "face",
		distance=float(result["distance"]),
		threshold=float(result["threshold"]),
		liveness=anti_spoofing,
	)
