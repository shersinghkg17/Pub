FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all files
COPY . .

# Compile C binary
RUN gcc -O3 bgmi.c -o bgmi -lpthread && chmod +x bgmi

# Run bot
CMD ["python", "telegram_bot.py"]
