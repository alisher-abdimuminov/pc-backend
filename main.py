from deepface import DeepFace

# from django.conf import settings

path = "/Users/ali/Projects/samdpi/practicum/backend/media/users/2026/09/hemis-320261100667.jpg"

faces = DeepFace.verify(
	img1_path="/Users/ali/Projects/samdpi/practicum/backend/media/users/2026/09/hemis-320261100667.jpg",
	img2_path="/Users/ali/Projects/samdpi/practicum/backend/media/attendance_attempts/2026/09/21/attendance_eRu5tDg.jpg",
	model_name="ArcFace",
	detector_backend="retinaface",
	distance_metric="cosine",
	enforce_detection=True,
	align=True,
	anti_spoofing=True,
	silent=True,
)

print(faces)
