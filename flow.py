from prefect import flow, get_run_logger

from prefect.deployments import Deployment
from prefect.infrastructure import Process

from models import SousChefBaseOrder

from sous_chef import RunPipeline, recipe_loader
from email_flow import send_run_summary_email

	

@flow()
def Buffet_TopTerms(data:SousChefBaseOrder):
	#data = SousChefBaseOrder(**data)
	recipe = open("topterms_recipe.yaml", "r").read()
	json_conf = recipe_loader.t_yaml_to_conf(recipe, **data.dict())
	json_conf["name"] = data.NAME
	run_data = RunPipeline(json_conf)
	send_run_summary_email({data.NAME:run_data}, data.EMAIL_TO)


if __name__ == '__main__':
	data = SousChefBaseOrder(
		QUERY="northampton massachusetts",
		S3_PREFIX="first_buffet_test"
		)

	recipe = open("topterms_recipe.yaml", "r").read()
	json_conf = recipe_loader.t_yaml_to_conf(recipe, **data.dict())
	json_conf["name"] = data.NAME
	run_data = RunPipeline(json_conf)