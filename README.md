Sous-Chef Buffet
================

A place to experiment with an interface for self-service sous-chef. 

flow.py 
	* this defines the code that runs in prefect- including sous-chef setup and runtime.

prefect.yaml
	* this defines how flow.py is deployed into prefect.

souschef_client.py
	* this defines an interface to interact with that flow once it is deployed, and other details about the prefect environment

api.py
	* a fastapi wrapper around souschef_client

buffet.py
	* This is a streamlit application that makes it super easy to provide query parameters for a sous-chef flow and to run them.
	* streamlit's syncronicity requirements are kind of a bummer though- and the final version of this will be a lightweight vue.js app
	* leaning on api.py 
	

app.py
	* A flask app (with vue frontend in buffet_app) to try and run the rest of the distance that buffet.py can't quite fill
	