FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml README.md API.md ./
COPY src ./src
COPY static ./static
RUN pip install --no-cache-dir .
ENV PYTHONUNBUFFERED=1
CMD ["sh", "-c", "uvicorn iett_tracker.app:app --host 0.0.0.0 --port ${PORT:-8000} --app-dir src"]
