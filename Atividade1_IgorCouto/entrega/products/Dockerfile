FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY products/ ./products/
CMD ["sh", "-c", "uvicorn products.main:app --host 0.0.0.0 --port ${PORT:-5002}"]
