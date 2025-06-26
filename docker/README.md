# Demo Deployment Steps
This is how Paige set this up during dev. - Everything here is set up to be run from the project root.  

### Setup, Fetch secrets.

Later steps will require the client libraries installed, so `pip install -r requirements-client.txt` - masomenos however you manage your environments. 

Secret values are stored in a private config repo, as in our other projects. Clone into the root directory

`git clone git@github.com:mediacloud/sous-chef-config.git`

### docker-compose up
Run docker-compose to lift up the services- they are:
1. `prefect-server`, unmodified from prefect
2. `prefect-worker`, also out-of-the-box, pretty much
3. `prefect-config`, ephemeral setup container, 
4. `kitchen-api`, the actual final kitchen api endpoint. 

`sudo docker-compose -f docker/docker-compose.yaml up -d`

The prefect server can be heathchecked with a `curl localhost:4200/api/health` (returns 200 true)

### CLI setup and validation
Prefect has this notion of 'profiles'- we need to have the correct one set up before step 4. 

`sudo prefect profile create kitchen-dev`

`sudo prefect config set PREFECT_API_URL=http://localhost:4200/api`

`sudo prefect profile use 'kitchen-dev'`

(Obviously, the prefect_api_url needs to match what is configured in the docker-compose file- this is just the default)

If everything is working, `sudo prefect work-pool ls` should show a work-pool named `kitchen-work-pool` (this validates both that your profile is setup and that the prefect-config ran correctly above. 

### Deploy the flow to the prefect instance
If the prefect server is up and our profile is correctly configured:
`sudo prefect --no-prompt deploy --name kitchen-base` 

### Configure the buffet instance locally for testing the kitchen api 

In the environment you're testing in, you need three environment variables set: 
> SC_API_BASE_URL="http://localhost:8000/"
> 
> SC_API_AUTH_EMAIL=
> 
> SC_API_AUTH_KEY=
>

(as above, the base_url should match how the `kitchen-api` is actually deployed.)

`python buffet.py auth` will sync the client to the kitchen (will interactively prompt for the email/key if not already provided in the environment)

`python buffet.py status` will generally show if all the moving pieces are happy 

### Test the kitchen
This sample incantation runs a keyword extraction job. 

`python buffet.py recipes start keywords QUERY seltzer COLLECTIONS ["34412234"] START_DATE 2025-05-01 END_DATE 2025-06-01 NAME kitchen_test`

It should return a json object with an 'id' field

`python buffet.py runs list` to check the status of a job- will show metadata and state (PENDING/RUNNING/FAILED etc- is empty when completed for now)

`python buffet.py runs artifacts $RUN_ID` to get the output of the job (a link to an output bucket)

