FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd --system app && useradd --system --gid app app
COPY --chown=app:app . .
USER app

EXPOSE 5000

CMD ["gunicorn", "--chdir", "/app/src",  "--workers", "2", "--bind", "0.0.0.0:5000", "--access-logfile", "-", "--error-logfile", "-", "--capture-output", "--no-control-socket", "flask_app:app"]