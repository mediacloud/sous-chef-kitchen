from prefect import flow, get_run_logger

from prefect.deployments import Deployment
from prefect.infrastructure import Process

from pydantic import BaseModel, computed_field

from sous_chef import RunPipeline, recipe_loader
from email_flow import send_run_summary_email


class SousChefBaseOrder(BaseModel):
	QUERY:str = ""
	START_DATE_STR:str = "2024-01-01"
	END_DATE_STR:str = "2024-02-01"
	COLLECTIONS: list[str] = ["34412234"]
	NAME: str = "Sous-Chef-Run"
	S3_PREFIX:str="mediacloud"
	EMAIL_TO:list[str] = ["paige@mediacloud.org"]


	#We'll want some additional validators here on the date probably
	#or maybe to have a transformed output function instead of relying on .dict()
	@computed_field()
	def START_DATE(self) -> str:
		return f"'{self.START_DATE_STR}'"

	@computed_field()
	def END_DATE(self) -> str:
		return f"'{self.END_DATE_STR}'"
	

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