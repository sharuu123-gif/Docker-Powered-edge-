# ==============================================================================
# Edge Computing Laboratory Project: Dockerfile
# Containerizing an Edge Application with Docker
# ==============================================================================

# Use an official, lightweight Python 3.11 runtime
FROM python:3.11-slim

# Maintainer / Metadata
LABEL maintainer="Edge Computing Lab"
LABEL description="Containerized Edge Gateway Application running Flask"

# Set environment variables:
# 1. Prevent Python from writing .pyc files
# 2. Prevent Python from buffering stdout/stderr (real-time terminal logging)
# 3. Mark environment as running inside a Docker container
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DOCKER_CONTAINER=true
ENV PORT=5000

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install dependencies without caching to keep the image minimal and clean
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project source code and assets into the container
COPY . .

# Expose port 5000 to allow network communication from the host system
EXPOSE 5000

# Health check to ensure the edge container is responsive
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/status')" || exit 1

# Launch the Flask Edge Application
CMD ["python", "app.py"]
