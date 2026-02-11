#!/bin/sh
# Override sous-chef installation if SOUS_CHEF_REF is set
# This script is called by Prefect deployment steps to optionally
# install a specific branch/tag/SHA of sous-chef instead of the default

if [ -n "${SOUS_CHEF_REF:-}" ]; then
    echo "Overriding sous-chef with ref ${SOUS_CHEF_REF}"
    pip install --no-cache-dir --force-reinstall "sous-chef @ git+https://github.com/mediacloud/sous-chef@${SOUS_CHEF_REF}"
else
    echo "SOUS_CHEF_REF not set; using default sous-chef from requirements-flow.txt"
fi
