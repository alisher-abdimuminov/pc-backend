from django.apps import AppConfig


class UsersConfig(AppConfig):
	name = "users"
	verbose_name = "Foydalanuvchilar"

	def ready(self):
		from .audit import connect_signals

		connect_signals()
