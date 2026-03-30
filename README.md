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

Edit `.env` and set your own values for `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD`. Generate a secret key with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Use the same command to generate `POSTGRES_PASSWORD`.

For production, also set:
```
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=yourdomain.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://yourdomain.com
```

Note: `DJANGO_ALLOWED_HOSTS` takes the bare domain (e.g. `yourdomain.com`), while `DJANGO_CSRF_TRUSTED_ORIGINS` requires the scheme prefix (e.g. `https://yourdomain.com`).

## Development

```bash
docker compose up --build
```

This starts two containers:
- **django** — Gunicorn on port 8000
- **db** — PostgreSQL 15

Access the app at http://localhost:8000/patents/

## Production

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build
```

This starts three containers:
- **nginx** — Reverse proxy on ports 80/443, serves static and media files
- **django** — Gunicorn (internal only, port 8000 not exposed to host)
- **db** — PostgreSQL 15

Migrations and static file collection run automatically on startup.

## Create a Superuser (optional)

```bash
docker exec -it django python manage.py createsuperuser
```

## Access

| Page | Development | Production |
|------|-------------|------------|
| App | http://localhost:8000/patents/ | http://localhost/patents/ |
| Admin | http://localhost:8000/admin/ | http://localhost/admin/ |
| Sign up | http://localhost:8000/users/signup/ | http://localhost/users/signup/ |

## Stop

```bash
docker compose down
```

Add `-v` to also delete database and media volumes:

```bash
docker compose down -v
```

## Deploy with ngrok

If you don't have a public IP or port forwarding, you can use [ngrok](https://ngrok.com/) to expose the app. Ngrok handles HTTPS automatically — no certbot needed.

1. Start the production stack:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build
   ```

2. In a separate terminal, start ngrok:
   ```bash
   ngrok http 80
   ```

3. Copy the ngrok URL (e.g. `https://abc123.ngrok-free.app`) and update `.env`:
   ```
   DJANGO_ALLOWED_HOSTS=abc123.ngrok-free.app
   DJANGO_CSRF_TRUSTED_ORIGINS=https://abc123.ngrok-free.app
   ```

4. Restart the django container to pick up the new settings:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml restart django
   ```

Note: The free ngrok tier assigns a random URL on each restart. For a stable deployment, use a VPS with a public IP and the Let's Encrypt setup below.

## HTTPS (Let's Encrypt)

1. Set `DOMAIN` in `.env` to your domain name and update `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` accordingly.

2. Start the stack:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
   ```

3. Obtain certificates:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm certbot certonly --webroot -w /var/www/certbot -d yourdomain.com
   ```

4. In `nginx/nginx.conf`: uncomment the HTTPS server block (replace `yourdomain.com` with your domain) and uncomment the `return 301` redirect in the HTTP block.

5. Restart nginx:
   ```bash
   docker compose restart nginx
   ```

6. To renew certificates:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm certbot renew && docker compose restart nginx
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
| `DOMAIN` | Domain name for HTTPS/certbot | `localhost` |