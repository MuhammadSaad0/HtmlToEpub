FROM python:3.12-slim

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PATH=/root/.local/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
    calibre \
    default-jre \
    git \
    python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir --user pipx \
    && python3 -m pipx ensurepath

RUN pipx install --python=3.12 --fetch-missing-python standardebooks

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

WORKDIR /app
COPY script.py /app/script.py

ENTRYPOINT ["python3", "/app/script.py"]