FROM python:3.11-slim

WORKDIR /app

# Copy requirements trước (tận dụng Docker layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy code (layer này sẽ được override bởi volume mount trong dev)
COPY . .

EXPOSE 8000

# Dùng uvicorn với reload=True (đã có trong main.py)
CMD ["python", "main.py"]