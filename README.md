# ARPatent

A web application for uploading 3D patent models (OBJ, STL, STP, IGES, GLB), converting them to GLB format, and serving them for AR viewing via QR codes.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)

## Clone

```bash
git clone https://github.com/samoosama1/ARDesign-server.git
cd ARDesign-server
```

## Configure

```bash
cd backend
cp .env.example .env
```

Edit `.env` and set your own values for `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD`.

For production, also set:
```
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=yourdomain.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://yourdomain.com
```

## Start

```bash
docker compose up --build
```

This starts two containers:
- **django** — Gunicorn serving the app on port 8000
- **db** — PostgreSQL 15

Migrations run automatically on startup.

## Create a Superuser (optional)

```bash
docker exec -it django python manage.py createsuperuser
```

## Access

- App: http://localhost:8000/patents/
- Admin: http://localhost:8000/admin/
- Sign up: http://localhost:8000/users/signup/

## Stop

```bash
docker compose down
```

Add `-v` to also delete database and media volumes:

```bash
docker compose down -v
```

## Environment Variables

Defined in `backend/.env` (not committed). See `.env.example` for the template.

| Variable | Description | Default |
|----------|-------------|---------|
| `DJANGO_SECRET_KEY` | Django secret key for cryptographic signing | `change-me-in-production` |
| `DJANGO_DEBUG` | Enable debug mode | `True` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed hostnames | `localhost` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated trusted origins for CSRF | *(empty)* |
| `POSTGRES_DB` | Database name | `arpatentdb` |
| `POSTGRES_USER` | Database user | `myuser` |
| `POSTGRES_PASSWORD` | Database password | *(required)* |