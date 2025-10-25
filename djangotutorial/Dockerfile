FROM youndria/arpatent:1.1

WORKDIR /app/django

# Install venv support
RUN apt-get update && apt-get install -y python3-venv python3-pip --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*


COPY requirements.txt .

RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

ENV DJANGO_SETTINGS_MODULE=mysite.settings
ENV PYTHONUNBUFFERED=1
ENV PATH="/opt/venv/bin:$PATH"

ENTRYPOINT ["gunicorn"]
CMD ["--bind", "0.0.0.0:8000", "mysite.wsgi:application"]
