FROM youndria/arpatent:1.1

WORKDIR /app/django

# Install venv support
RUN apt-get update && apt-get install -y python3-venv python3-pip gettext libmagic1 --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

ENV DJANGO_SETTINGS_MODULE=config.settings
ENV PYTHONUNBUFFERED=1
ENV PATH="/opt/venv/bin:$PATH"
ENV TZ=Europe/Istanbul

RUN echo $TZ > /etc/timezone && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata

COPY entrypoint.sh /app/django/entrypoint.sh
RUN chmod +x /app/django/entrypoint.sh

ENTRYPOINT ["/app/django/entrypoint.sh"]
CMD ["--bind", "0.0.0.0:8000", "config.wsgi:application", "--timeout", "600"]