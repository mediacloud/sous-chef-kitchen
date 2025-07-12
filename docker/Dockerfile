# Use an official Python image
FROM python:3.11-slim

# app home directory in image
ENV APP=/app

# Set work directory
WORKDIR ${APP}

# NOTE! All COPY commands relative to compose yaml file "context"
# (which defines the root dir accessible by build)

# Install system dependencies (if needed)
RUN apt-get update && apt-get install -y build-essential
RUN apt-get install -y git
# Copy requirements and install
COPY requirements-server.txt ${APP}/requirements-server.txt
RUN pip install --no-cache-dir -r requirements-server.txt

COPY sous_chef_kitchen/ ${APP}/sous_chef_kitchen/
COPY recipes/ ${APP}/recipes/
COPY prefect.yaml ${APP}
COPY docker/prefect-config.py ${APP}

# Expose the port FastAPI will run on
EXPOSE 8000

# No CMD or ENV_VARS needed since docker-compose provides both. 
