FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Compile bgmi.c to binary
RUN gcc bgmi.c -o bgmi -pthread -O3

RUN chmod +x bgmi

ENV PORT=8080
ENV PYTHONUNBUFFERED=1

EXPOSE $PORT

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} --access-logfile - --error-logfile - app:app"]
