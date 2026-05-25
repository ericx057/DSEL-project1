FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

RUN adduser --disabled-password --gecos "" cisuser \
    && mkdir -p /data \
    && chown -R cisuser:cisuser /app /data

USER cisuser

EXPOSE 8000

CMD ["uvicorn", "src.gateway.bootstrap:app", "--host", "0.0.0.0", "--port", "8000"]
