# from rss-fetcher, from mc-providers (removed make test), from es-tools, from sitemap-tools

# to create development environment: `make`
# to run pre-commit linting/formatting: `make lint`

VENVDIR=venv
VENVBIN=$(VENVDIR)/bin
VENVDONE=$(VENVDIR)/.done

help:
	@echo Usage:
	@echo "make install -- installs pre-commit hooks, dev environment"
	@echo "make lint -- runs pre-commit checks"
	@echo "make requirements -- create requirements.txt from pyproject.toml"
	@echo "make update -- update .pre-commit-config.yaml"
	@echo "make clean -- remove development environment"
	@echo "make local-deploy-prep -- prepare prefect.yaml.local from template with current branch"
	@echo "make local-deploy -- deploy to Prefect using local configuration"

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

## prepare local deployment configuration
local-deploy-prep:
	@chmod +x scripts/prepare-local-deployment.sh
	@./scripts/prepare-local-deployment.sh

## deploy to Prefect using local configuration
local-deploy: prefect.yaml.local
	@if [ ! -f prefect.yaml.local ]; then \
		echo "Error: prefect.yaml.local not found. Run 'make local-deploy-prep' first."; \
		exit 1; \
	fi
	@echo "Deploying with local configuration..."
	@prefect deploy --name kitchen-base --prefect-file prefect.yaml.local
	@echo "✅ Deployment complete"

.PHONY: local-deploy-prep local-deploy
