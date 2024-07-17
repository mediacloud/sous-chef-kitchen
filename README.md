Sous-Chef Buffet
================

A place to experiment with an interface for self-service sous-chef. 


flow.py 
	- this defines the code that runs in prefect- including sous-chef setup and runtime.

prefect.yaml
	- this defines how flow.py is deployed into prefect.

prefect_client.py
	- this defines an interface to interact with that flow once it is deployed.

run_test.py 
	- this will read the pydantic model from flow.py and use it to define an argparse interface to run the flow via the prefect_client
		currently not doing that first part but honestly that's not neccesary

buffet.py
	- this will read the pydantic model from flow.py and use it to define a simple web interface to run the model and monitor its status 



There's some extra thought needed about: getting API keys in there, flow status, retrieving flow output for the ui, etc...
But the basic prefect_client loop is here now, plus a demo of a streamlit app to run it! This is in demo status officially!