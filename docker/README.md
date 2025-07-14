# Demo Deployment Steps
This a reproducable process for dev deployment. - Everything here is set up to be run from the project root.  

###
`sudo ./docker/deploy.sh` will build and tag a docker image, interpolate some environment variables into the docker-swarm.yaml configuration, and then launch a docker-swarm instance with all of the moving parts. If that runs successfully, you're ready to test. 

### Configure the buffet instance locally for testing the kitchen api 

To test a stack, you just need to configure your environment so that the buffet is pointing at the right place. Replace "...localhost..." with the details for your environment
(on bly for a dev instance it's http://172.17.0.1:8020)

> SC_API_BASE_URL="http://localhost:8000/"


`python buffet.py auth` will sync the client to the kitchen (will interactively prompt for the email/key if not already provided in the environment)

`python buffet.py status` will generally show if all the moving pieces are happy 

### Test the kitchen

`python buffet.py recipes list` will show you all of the recipes currently supported in the kitchen, with a short description of their function.

`python buffet.py recipes schema $RECIPE_NAME` will show you the JSON schema that a recipe expects.

To start, for example, a keyword extraction job:

`python buffet.py recipes start keywords QUERY seltzer COLLECTIONS ["34412234"] START_DATE 2025-05-01 END_DATE 2025-06-01 NAME kitchen_test`

If successful, this should return a json object with an 'id' field

`python buffet.py runs list` Shows the status of all currently running jobs

`python buffet.py runs inspect $RUN_ID` shows the status of a specific job.

`python buffet.py runs artifacts $RUN_ID` shows all of the output related to a job


