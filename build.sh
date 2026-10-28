
#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate

python manage.py shell <<'PY'
import os
from django.contrib.auth import get_user_model

User = get_user_model()

username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")
password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

if not username or not password:
    print("Superuser creation skipped: credentials are not configured.")
elif User.objects.filter(username=username).exists():
    print("Superuser already exists; no changes made.")
else:
    User.objects.create_superuser(
        username=username,
        email=email,
        password=password,
    )
    print("Initial superuser created successfully.")
PY
