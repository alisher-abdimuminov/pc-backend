import requests
from django.conf import settings
from django.db import transaction

from users.models import Group


def sync_hemis_groups():
	token = settings.HEMIS_GROUPS_TOKEN

	if not token:
		raise ValueError("HEMIS_GROUPS_TOKEN sozlanmagan.")

	headers = {
		"Accept": "application/json",
		"Authorization": f"Bearer {token}",
	}

	page = 1
	limit = 200

	remote_groups = {}

	while True:
		response = requests.get(
			settings.HEMIS_GROUPS_URL,
			headers=headers,
			params={
				"limit": limit,
				"page": page,
			},
			timeout=30,
		)

		if response.status_code != 200:
			raise ValueError(
				f"HEMIS group-list xatolik: "
				f"{response.status_code} "
				f"{response.text[:500]}"
			)

		payload = response.json()

		if not payload.get("success"):
			raise ValueError(
				payload.get("error") or "HEMIS group-list xatolik qaytardi."
			)

		data = payload.get("data") or {}

		items = data.get("items") or []

		for item in items:
			hemis_id = item.get("id")
			name = item.get("name")

			if not hemis_id or not name:
				continue

			remote_groups[int(hemis_id)] = {
				"hemis_id": int(hemis_id),
				"name": name.strip(),
			}

		pagination = data.get("pagination") or {}

		page_count = int(pagination.get("pageCount") or 1)

		if page >= page_count:
			break

		page += 1

	created_count = 0
	updated_count = 0
	unchanged_count = 0

	with transaction.atomic():
		for group_data in remote_groups.values():
			hemis_id = group_data["hemis_id"]
			name = group_data["name"]

			# Avval HEMIS ID orqali qidiramiz.
			group = Group.objects.filter(hemis_id=hemis_id).first()

			if group:
				if group.name != name:
					group.name = name

					group.save(
						update_fields=[
							"name",
						]
					)

					updated_count += 1
				else:
					unchanged_count += 1

				continue

			# Oldindan qo'lda xuddi shu nom bilan
			# yaratilgan group bo'lishi mumkin.
			group = Group.objects.filter(name=name).first()

			if group:
				group.hemis_id = hemis_id

				group.save(
					update_fields=[
						"hemis_id",
					]
				)

				updated_count += 1

				continue

			Group.objects.create(
				hemis_id=hemis_id,
				name=name,
			)

			created_count += 1

	return {
		"total": len(remote_groups),
		"created": created_count,
		"updated": updated_count,
		"unchanged": unchanged_count,
	}
