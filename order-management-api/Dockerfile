FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files first for better layer caching
# Note: README.md is required by pyproject.toml, so copy it before installing
COPY pyproject.toml ./
COPY README.md ./

# Install dependencies (this layer will be cached if dependencies don't change)
RUN uv pip install --system -e .

# Copy application code and data
COPY src/ ./src/
COPY data/ ./data/

# Create database directory
RUN mkdir -p ./data/temp

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
