# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Install curl for the HEALTHCHECK, then clean up apt caches to keep the image small
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user and set cache directory permissions
RUN useradd --create-home --shell /bin/bash app && \
    mkdir -p /home/app/.cache && \
    chown -R app:app /home/app/.cache && \
    chown -R app:app /app

# NVIDIA API configuration — override at runtime (docker run -e / platform secrets).
# NVIDIA_API_KEY has no default: the app fails fast at startup if it's unset.
# All inference (chat, vision/OCR, and embeddings) runs via NVIDIA's hosted API —
# no local model download or GPU is required.
ENV NVIDIA_MODEL=openai/gpt-oss-20b
ENV NVIDIA_VISION_MODEL=nvidia/nemotron-3-nano-omni-30b-a3b-reasoning
ENV NVIDIA_EMBEDDING_MODEL=nvidia/nv-embedqa-e5-v5

# Copy the requirements file into the container
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
# (.dockerignore excludes .env, venv/, __pycache__, and other local-only files)
COPY . .

# Change ownership of all files to app user
RUN chown -R app:app /app

# Switch to non-root user
USER app

# Expose the port your app runs on
EXPOSE 8000

# Verify the app is actually serving requests, not just that the process is alive
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://127.0.0.1:${PORT:-8000}/ || exit 1

# Command to run the application; most PaaS platforms (Render, Fly, HF Spaces) set PORT
CMD sh -c "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"