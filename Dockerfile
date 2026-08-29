# Stage 1: Build the frontend
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Build the Python app
FROM python:3.12-slim

# Install system dependencies: build tools for mysqlclient, Tesseract OCR
# for council-tax evidence extraction (debt_app/integrations/council_tax_evidence.py)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    default-libmysqlclient-dev \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Copy the frontend build to a location Django can serve
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Set non-sensitive environment variables for collectstatic
ENV DEBUG=False
ENV ALLOWED_HOSTS=localhost

# Run collectstatic with a temporary dummy secret key to avoid security warnings
RUN SECRET_KEY=build-placeholder-key python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "debt_project.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]
