# Niva API image. The build context is the repository root.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

# curl stays in the image for container healthchecks.
# Compilers are installed only for this step and removed afterwards.
COPY requirements.txt /workspace/requirements.txt
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl build-essential libffi-dev \
    && pip install --no-cache-dir -r /workspace/requirements.txt \
    && apt-get purge -y --auto-remove build-essential libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend /workspace/backend

EXPOSE 8000

# --reload watches the backend bind mount used in local development.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--proxy-headers", "--forwarded-allow-ips", "*", "--app-dir", "backend"]
