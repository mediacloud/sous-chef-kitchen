# from rss-fetcher, from mc-providers (removed make test), from es-tools, from sitemap-tools

# to create development environment: `make`
# to run pre-commit linting/formatting: `make lint`

VENVDIR=venv
VENVBIN=$(VENVDIR)/bin
VENVDONE=$(VENVDIR)/.done

SOUS_CHEF_REF?=v3.0.5
SOUS_CHEF_REPO?=https://github.com/mediacloud/sous-chef
KITCHEN_PORT?=8000

help:
	@echo Usage:
	@echo "make install -- installs pre-commit hooks, dev environment"
	@echo "make lint -- runs pre-commit checks"
	@echo "make requirements -- create requirements.txt from pyproject.toml"
	@echo "make update -- update .pre-commit-config.yaml"
	@echo "make clean -- remove development environment"
	@echo "make local-deploy-prep -- prepare prefect.yaml.local from template with current branch"
	@echo "make local-deploy -- deploy to Prefect using local configuration"
	@echo "make dev-install -- install kitchen server deps with sous-chef from git ref (default: $(SOUS_CHEF_REF))"
	@echo "make dev-server -- run kitchen API server locally with sous-chef from git ref"

## run pre-commit checks on all files
lint:	$(VENVDONE)
	$(VENVBIN)/pre-commit run --all-files

# create venv with project dependencies
# --editable skips installing project sources in venv
# pre-commit is in dev optional-requirements
install $(VENVDONE): $(VENVDIR) Makefile pyproject.toml
	$(VENVBIN)/python3 -m pip install --editable '.[dev]'
	$(VENVBIN)/pre-commit install
	touch $(VENVDONE)

$(VENVDIR):
	python3 -m venv $(VENVDIR)

## update .pre-commit-config.yaml
update:	$(VENVDONE)
	$(VENVBIN)/pre-commit autoupdate

## build requirements-*.txt files
requirements requirements-flow.txt: pyproject.toml Makefile
	$(VENVBIN)/pip-compile --extra sous-chef -o requirements-flow.txt.tmp --strip-extras pyproject.toml
	mv requirements-flow.txt.tmp requirements-flow.txt

## clean up development environment
clean:
	-$(VENVBIN)/pre-commit clean
	rm -rf $(VENVDIR) build *.egg-info .pre-commit-run.sh.log \
		__pycache__ .mypy_cache

## install kitchen server dependencies with sous-chef from git ref
dev-install: $(VENVDONE)
	@echo "Installing sous-chef from git ref: $(SOUS_CHEF_REF)"
	@echo "Repository: $(SOUS_CHEF_REPO)"
	@echo "Removing any existing sous-chef installation from this venv (if present)..."
	-$(VENVBIN)/pip uninstall -y sous-chef >/dev/null 2>&1 || true
	$(VENVBIN)/pip install --upgrade pip setuptools wheel flit packaging
	$(VENVBIN)/pip install "sous-chef @ git+$(SOUS_CHEF_REPO)@$(SOUS_CHEF_REF)"
	$(VENVBIN)/pip install --editable '.[server]'
	@echo "✅ Development dependencies installed with sous-chef@$(SOUS_CHEF_REF)"

## run kitchen API server locally with sous-chef from git ref
dev-server: dev-install
	@echo "Starting kitchen API server on port $(KITCHEN_PORT)"
	@echo "Using sous-chef from git ref: $(SOUS_CHEF_REF)"
	@echo "API will be available at: http://localhost:$(KITCHEN_PORT)"
	@echo "Press Ctrl+C to stop"
	$(VENVBIN)/uvicorn sous_chef_kitchen.kitchen.api:app \
		--host 0.0.0.0 \
		--port $(KITCHEN_PORT) \
		--reload \
		--log-level info

## prepare local deployment configuration
local-deploy-prep:
	@chmod +x dev/prepare-local-deployment.sh
	@./dev/prepare-local-deployment.sh

## deploy to Prefect using local configuration
local-deploy: prefect.yaml.local
	@if [ ! -f prefect.yaml.local ]; then \
		echo "Error: prefect.yaml.local not found. Run 'make local-deploy-prep' first."; \
		exit 1; \
	fi
	@echo "Deploying with local configuration..."
	@prefect deploy --name kitchen-base --prefect-file prefect.yaml.local
	@echo "✅ Deployment complete"

.PHONY: local-deploy-prep local-deploy dev-install dev-server
