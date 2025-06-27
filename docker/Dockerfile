# Use an official Python image
FROM python:3.11-slim

# Set work directory
WORKDIR /app

# Install system dependencies (if needed)
RUN apt-get update && apt-get install -y build-essential
RUN apt-get install -y git
# Copy requirements and install
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

# Copy your code
COPY ../sous_chef_kitchen/ sous_chef_kitchen/
COPY ../recipes/ recipes/
COPY ../prefect.yaml .
COPY ../docker/prefect-config.py .

# Expose the port FastAPI will run on
EXPOSE 8000

# No CMD or ENV_VARS needed since docker-compose provides both. 
