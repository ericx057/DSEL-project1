FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

COPY requirements.txt .
COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

COPY src ./src

RUN adduser --disabled-password --gecos "" cisuser \
    && mkdir -p /data \
    && chown -R cisuser:cisuser /app /data

USER cisuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

CMD ["uvicorn", "src.gateway.bootstrap:app", "--host", "0.0.0.0", "--port", "8000"]
