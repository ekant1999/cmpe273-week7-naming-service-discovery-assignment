FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY client.py .

# -u: unbuffered output so logs stream in real time with `docker compose logs -f client`
CMD ["python3", "-u", "client.py"]
