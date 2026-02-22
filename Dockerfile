# 1. Use the official Python 3.10 slim image (matches your version)
FROM python:3.10-slim

# 2. Set the working directory inside the container
WORKDIR /app

# 3. Copy requirements first (This caches the installation layer)
COPY requirements.txt .

# 4. Install dependencies
# --no-cache-dir keeps the image small
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of your code
# (The .dockerignore file will stop .env from being copied here)
COPY . .

# 6. Expose the app port
EXPOSE 8000

# 7. Run the application
# Use fastapi_app:app (not main:app) and honor Cloud Run PORT if provided
CMD ["sh", "-c", "uvicorn fastapi_app:app --host 0.0.0.0 --port ${PORT:-8000}"]
