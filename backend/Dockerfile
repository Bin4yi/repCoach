FROM python:3.12-slim
WORKDIR /app
# libgl/glib are needed by MediaPipe's native libs
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Cache the pose model at build time so first request is fast
RUN python scripts/download_model.py || echo "model download skipped (will retry at runtime)"
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
