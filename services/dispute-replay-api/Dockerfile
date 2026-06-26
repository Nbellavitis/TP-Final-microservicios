FROM python:3.12-slim

ENV PORT=8080 \
    SERVICE_CONFIG=/app/service.json \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY devops-checkpoint/runtime/app.py /app/app.py
COPY services/dispute-replay-api/service.json /app/service.json

RUN useradd --create-home --uid 10001 appuser
USER 10001

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2).read()"

CMD ["python", "/app/app.py"]