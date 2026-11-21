import os
BASE = os.path.dirname(os.path.abspath(__file__))
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me-in-production")
DATABASE = os.environ.get("DATABASE", os.path.join(BASE, "examguard.db"))
# Initial DEMO admin. Seeded once (password is hashed). Override via env vars; change it in Settings after login.
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "Arish15@gmail.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Heam@#$089")
ADMIN_NAME = "Administrator"
FACE_ABSENCE_LIMIT = 2      # 3rd sustained absence terminates
ABSENCE_SECONDS = 6         # grace before absence counts
PHONE_CONFIDENCE = 0.60
EVENT_RETENTION_DAYS = 90
