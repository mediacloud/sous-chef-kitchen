# Sous-Chef Kitchen

A job API around Prefect for driving Sous-Chef, Mediacloud's internal data pipeline process.


## Structure

the ci/cd script at 'docker/deploy.sh' will launch a docker service containing four services:
1: kitchen-api: the fastapi server defined in `sous_chef_kitchen/kitchen/api.py` - interface to the outside world.
	Indexes available sous-chef runs, fields requests from external services, etc
2. prefect-server: a prefect server process- orchestrates sous-chef runs.
3. prefect-worker: a prefect worker process- actually exectures sous-chef runs using a dedicated worker image (`docker/Dockerfile.worker`) with flow dependencies and source baked at build time.
4. prefect-config: an ephemeral process that configures the prefect-server and ensures that the pieces are all talking nice.



## Dev/Deployment

Deployments are managed via a single ci/cd script found at `docker/deploy.sh`. Launches personal dev environments / staging / production based on checked-out branch. NB: The version of sous-chef used in this context is pinned in pyproject.toml. For dev contexts, this can be overridden with `docker/deploy.sh -s SOUS_CHEF_REF` if you provide the git tag of the sous-chef library you want to test against. This override is applied at image build time for the worker image (not as a runtime install), so deploy builds will take longer when used.

Before running deploy, install development dependencies in your active virtual environment:
`pip install .[dev]`

In deploy contexts, version bump main by rebuilding requirements-flow.text, with `make requirements` whenever you bump the version in pyproject.toml.


## invoke the client

cli via just `python buffet.py` does it, self-documenting and all that. Requires setting a `SC_API_BASE_URL` value in the environment- will update default to prod when available.
The consumer client `SousChefKitchenAPIClient` lives in `sous_chef_kitchen/client/menu.py`


# Sous-Chef a la carte
