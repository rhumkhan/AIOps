FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered output
# so container logs appear immediately.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (this layer is cached unless
# requirements.txt changes, making rebuilds fast).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code.
COPY . .

# Run the ASGI server.  --host 0.0.0.0 makes it reachable from
# outside the container (Docker networking).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
