FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY orders/ ./orders/
CMD ["uvicorn", "orders.main:app", "--host", "0.0.0.0", "--port", "5003"]
