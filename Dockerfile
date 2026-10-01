FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

ENV HOME=/home/app

WORKDIR /app

RUN apt-get update && apt-get install -y \
	build-essential \
	gcc \
	libpq-dev \
	libgl1 \
	libglib2.0-0 \
	libgomp1 \
	libjpeg62-turbo-dev \
	zlib1g-dev \
	ffmpeg \
	curl \
	gosu \
	&& rm -rf /var/lib/apt/lists/*

RUN useradd \
	--create-home \
	--shell /bin/bash \
	app

COPY requirements.txt /app/requirements.txt

RUN pip install \
	--upgrade pip \
	&& pip install \
	-r /app/requirements.txt

COPY . /app

RUN chmod +x /app/entrypoint.sh

RUN mkdir -p \
	/app/staticfiles \
	/app/media \
	/home/app/.deepface \
	&& chown -R app:app \
	/app \
	/home/app

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
