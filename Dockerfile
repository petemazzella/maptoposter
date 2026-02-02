# Map Poster API Dockerfile
# Wraps maptoposter as a REST API for automated poster generation

FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install UV package manager
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy entire repo
COPY . .

# Install maptoposter dependencies using UV
RUN uv sync

# Create posters output directory
RUN mkdir -p /app/posters

# Install API dependencies
RUN pip install --no-cache-dir -r api/requirements.txt

# Expose port
ENV PORT=8000
EXPOSE 8000

# Run the API from the api directory
CMD ["python", "api/main.py"]
