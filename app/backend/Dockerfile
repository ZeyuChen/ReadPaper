
# Use a base image with full TeX Live installation
# This image is large but necessary for compiling complex academic papers
FROM ghcr.io/xu-cheng/texlive-full:latest

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CLOUD_RUN_ENV=true

# Install Python and pip
# The base image is likely Alpine-based (common for texlive images)
RUN apk add --no-cache \
    python3 \
    py3-pip \
    curl \
    && python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements file
COPY app/backend/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
# We copy the entire 'app' directory to maintain package structure
COPY app/ /app/app/

# Create a simplified entrypoint script or just run uvicorn
# We need to make sure PYTHONPATH includes /app so `app.backend.main` works
ENV PYTHONPATH=/app

# Expose the port
# Expose the port (Cloud Run defaults to 8080)
EXPOSE 8080

# Run the application using the PORT environment variable
CMD ["sh", "-c", "uvicorn app.backend.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
