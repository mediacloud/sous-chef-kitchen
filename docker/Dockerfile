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

# Optional override for sous-chef git ref (branch/tag/SHA)
ARG SOUS_CHEF_REF=""
ENV SOUS_CHEF_REF=${SOUS_CHEF_REF}

# Copy pyproject file and install requirements
COPY pyproject.toml ${APP}/pyproject.toml

# Install core server dependencies (without sous-chef)
RUN pip install --no-cache-dir --editable '.[server]'

# Install sous-chef; allow override via SOUS_CHEF_REF for dev builds
RUN echo "Building with SOUS_CHEF_REF=${SOUS_CHEF_REF}" && \
    if [ -n "$SOUS_CHEF_REF" ]; then \
        echo "Installing sous-chef from git ref $SOUS_CHEF_REF"; \
        pip install --no-cache-dir "sous-chef @ git+https://github.com/mediacloud/sous-chef@$SOUS_CHEF_REF"; \
    else \
        echo "Installing default sous-chef extra from pyproject.toml"; \
        pip install --no-cache-dir --editable '.[sous-chef]'; \
    fi

COPY sous_chef_kitchen/ ${APP}/sous_chef_kitchen/
COPY docker/prefect.yaml ${APP}
COPY docker/prefect-config.sh ${APP}
COPY docker/prefect-config.py ${APP}

# Expose the port FastAPI will run on
EXPOSE 8000

# No CMD or ENV_VARS needed since docker-compose provides both.
