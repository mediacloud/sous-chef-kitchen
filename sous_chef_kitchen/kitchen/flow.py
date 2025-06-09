"""
Run (cook) recipe requests on Prefect using the kitchen-base flow.
"""

import os
from typing import Dict, List

import prefect
from prefect import flow, get_run_logger
from prefect.artifacts import create_table_artifact
from prefect.client.schemas.objects import FlowRun
from prefect.context import FlowRunContext

from sous_chef import RunPipeline, SousChefRecipe
from sous_chef_kitchen.shared.recipe import get_recipe_folder

BASE_TAGS = ["kitchen"]
PREFECT_DEPLOYMENT = os.getenv("SC_PREFECT_DEPLOYMENT", "kitchen-base")

#In this pattern, sc schema validation happens in chef.py when the SousChefRecipe is constructed.
#Therefore we just accept those parameters as a dict, and trust that it's correct. 
@flow(name=PREFECT_DEPLOYMENT)
async def kitchen_base(recipe_name: str, tags: List[str] = [], parameters:Dict = {}) -> FlowRun:
    logger = get_run_logger()
    tags += BASE_TAGS + [recipe_name]

    recipe_folder = get_recipe_folder(recipe_name)
    recipe_location = os.path.join(recipe_folder, "recipe.yaml")

    parsed_parameters = SousChefRecipe(recipe_location, parameters)
    
    with prefect.tags(*tags):
        run_data = RunPipeline(parsed_parameters)

    # TODO: add task to cleanup return value (remove full_text [pending authentication test])
    # TODO: add task to create_table_artifact from rundata after cleanup
    #Just printing the run data now to validate. 
    flow_run_name = FlowRunContext.get().flow_run.dict().get('name')
    for task, output in run_data.items():
        print(task)
        print(output)
        create_table_artifact(
            key = flow_run_name+"::"+task,
            table = output
        )
    
    return run_data
