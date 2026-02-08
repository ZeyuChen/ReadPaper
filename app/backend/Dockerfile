
# Use a base image with full TeX Live installation
# This image is large but necessary for compiling complex academic papers
FROM ghcr.io/xu-cheng/texlive-full:latest

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CLOUD_RUN_ENV=true

# Install Python and pip
# The base image is Debian-based
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Create and set working directory
WORKDIR /app

# Create a virtual environment
RUN python3 -m venv /opt/venv
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
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
