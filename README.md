# Sous-Chef Kitchen

A job API around Prefect for driving Sous-Chef, Mediacloud's internal data pipeline process. 


## Deployment

Deployments are managed via a single ci/cd script found at `docker/deploy.sh` - other details can be found in that directory


## invoke the client

cli via just `python buffet.py` does it, self-documenting and all that. Requires setting a `SC_API_BASE_URL` value in the environment- will update default to prod when available. 
The consumer client `SousChefKitchenAPIClient` lives in `sous_chef_kitchen/client/menu.py` 


# Sous-Chef a la carte
A second flow entrypoint for sous chef, mantained here for ease of deployment and versioning logic. 
The 'old school' way of interacting with sous-chef, where the recipes live somewhere in the cloud (S3, B2)
Launched/managed directly via prefect interface, not the kitchen api. 
For unusual one-off research data requests or testing. 
