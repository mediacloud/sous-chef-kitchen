# Use an official Python image
FROM python:3.11-slim

# Set work directory
WORKDIR /app

# Install system dependencies (if needed)
# RUN apt-get update && apt-get install -y build-essential

# Copy requirements and install
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

# Copy your code
COPY sous_chef_kitchen/ sous_chef_kitchen/
COPY a_la_carte/ a_la_carte/
COPY recipes/ recipes/
COPY buffet.py .
COPY lint.py .
COPY prefect.yaml .
COPY pyproject.toml .
COPY README.md .

# Expose the port FastAPI will run on
EXPOSE 8000

# No CMD or ENV_VARS needed since docker-compose provides both. 
