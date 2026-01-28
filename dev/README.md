# Local Prefect Development Setup

This directory contains files and scripts for setting up and running Prefect locally for development and testing.

## Files

- `prefect.yaml.local.in` - Template file for local Prefect deployment configuration
- `prepare-local-deployment.sh` - Script to generate `prefect.yaml.local` from the template with your current git branch

## Prerequisites

1. **Install dependencies:**
   ```bash
   pip install -e '.[server,sous-chef]'
   ```

2. **Set Prefect API URL (if using Prefect Cloud):**
   ```bash
   export PREFECT_API_URL=<your-prefect-cloud-url>
   ```
   If running a local Prefect server, this is typically `http://localhost:4200/api`

## Setup Steps

### 1. Start Prefect Server

If you're running Prefect locally (not using Prefect Cloud), start the server:

```bash
prefect server start
```

This will start the Prefect UI at `http://localhost:4200` by default.

### 2. Create Work Pool

Create a work pool for your flows:

```bash
prefect work-pool create --type process kitchen-work-pool
```

### 3. Start Worker

Start a worker to execute your flows:

```bash
prefect worker start --pool kitchen-work-pool
```

Keep this running in a separate terminal window.

### 4. Run Prefect Configuration (Docker Setup)

If you're using the Docker setup, run the configuration script to set up secrets and work pools:

```bash
# From the project root
cd docker
# Follow instructions in docker/README.md for running prefect-config
```

The `docker/prefect-config.py` script will:
- Wait for the Prefect API to be ready
- Create the work pool if it doesn't exist
- Set up required secrets (AWS credentials, B2 credentials, email credentials, MediaCloud API key)

### 5. Prepare Local Deployment

Generate the local deployment configuration file:

```bash
make local-deploy-prep
```

This will:
- Read your current git branch
- Interpolate the branch and repository URL into `prefect.yaml.local.in`
- Generate `prefect.yaml.local` in the project root

### 6. Deploy

Deploy your flows using the local configuration:

```bash
make local-deploy
```

This will deploy the `kitchen-base` flow using the generated `prefect.yaml.local` file.

## Workflow Summary

1. Start Prefect server: `prefect server start` (if local)
2. Create work pool: `prefect work-pool create --type process kitchen-work-pool`
3. Start worker: `prefect worker start --pool kitchen-work-pool`
4. Run docker config: `docker/prefect-config.py` (if using Docker)
5. Prepare deployment: `make local-deploy-prep`
6. Deploy: `make local-deploy`

## Troubleshooting

- **Work pool not found**: Make sure you've created the work pool before starting the worker
- **API connection errors**: Verify your `PREFECT_API_URL` is set correctly
- **Deployment fails**: Check that `prefect.yaml.local` exists (run `make local-deploy-prep` first)
- **Worker not picking up jobs**: Ensure the worker is running and connected to the same Prefect instance
