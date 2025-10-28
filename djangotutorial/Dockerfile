FROM youndria/arpatent:1.1

WORKDIR /app/django

# Install venv support
RUN apt-get update && apt-get install -y python3-venv python3-pip --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt gunicorn \
    && /opt/venv/bin/pip install --no-cache-dir trimesh==4.4.9 Pillow==10.4.0 numpy==1.26.4

COPY . .

ENV DJANGO_SETTINGS_MODULE=mysite.settings
ENV PYTHONUNBUFFERED=1
ENV PATH="/opt/venv/bin:$PATH"
ENV TZ=Europe/Istanbul

RUN echo $TZ > /etc/timezone && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata

ENTRYPOINT ["gunicorn"]
CMD ["--bind", "0.0.0.0:8000", "mysite.wsgi:application"]