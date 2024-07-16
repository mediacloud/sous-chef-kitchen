from prefect import flow, get_run_logger

from prefect.deployments import Deployment
from prefect.infrastructure import Process

from pydantic import BaseModel

from sous_chef import RunPipeline, recipe_loader


class SousChefBaseOrder(BaseModel):
	QUERY:str = ""
	START_DATE:str = "2024-01-01"
	END_DATE:str = "2024-02-01"
	COLLECTIONS: list[str] = ["34412234"]
	NAME: str = "Sous-Chef-Run"
	S3_PREFIX:str="mediacloud"
	EMAIL_TO:list[str] = ["paige@mediacloud.org"]

	#We'll want some validators here on the date, etc



@flow()
def Buffet_TopTerms(data:SousChefBaseOrder):
	#data = SousChefBaseOrder(**data)
	recipe = open("topterms_recipe.yaml", "r").read()
	json_conf = recipe_loader.t_yaml_to_conf(recipe, **data.dict())
	run_data = RunPipeline(json_conf)
	send_run_summary_email(run_data, data.EMAIL_TO)




if __name__ == '__main__':
	test = SousChefBaseOrder(
		query="*",
		)
	print(test.dict())
	recipe = open("topterms_recipe.yaml", "r").read()
	json_conf = recipe_loader.t_yaml_to_conf(recipe, **test.dict())
	print(json_conf)