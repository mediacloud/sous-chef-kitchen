# Sous-Chef Kitchen

A job API around Prefect for driving Sous-Chef, Mediacloud's internal data pipeline process. 


## Setup prefect

Requires the latest version of the prefect server running (3.2.x rn) - with the following blocks configured:

* AWS-credentials - 'aws-s3-credentials'
* Docker Registry Credentials - 'docker-auth'
* Email Server Credentials - 'paige-mediacloud-email-password'
* Github Credentials - 'sous-chef-read-only'
* Standard Secret (for the Mediacloud API key) - "mediacloud-api-key"


## deploy flow

The flow is the code that is actually excecuted by Prefect- this is a wrapper around the core Sous-Chef library. Deploy via `prefect deploy`
nb, prefect coordinates auth etc for client and server via 'profiles' in the environment- so all prefect interaction in the future will need that set up. 


## launch the Kitchen 

right now I'm launching via: `fastapi dev sous_chef_kitchen/kitchen/api.py `

## invoke the client

cli via just `python buffet.py` does it, self-documenting and all that. 
The consumer client `SousChefKitchenAPIClient` lives in `sous_chef_kitchen/client/menu.py` 


# Sous-Chef a la carte
A second flow entrypoint for sous chef, mantained here for ease of deployment and versioning logic. 
The 'old school' way of interacting with sous-chef, where the recipes live somewhere in the cloud (S3, B2)
Launched/managed directly via prefect interface, not the kitchen api. 
For unusual one-off research data requests or testing. 