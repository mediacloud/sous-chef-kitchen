"""
Run (cook) recipe requests on Prefect using the kitchen-base flow.
"""

import os
from typing import Dict, List

import prefect
from prefect import flow
from prefect.client.schemas.objects import FlowRun

from sous_chef import RunPipeline, SousChefRecipe
from sous_chef_kitchen.shared.recipe import get_recipe_folder

BASE_TAGS = ["kitchen"]
PREFECT_DEPLOYMENT = os.getenv("SC_PREFECT_DEPLOYMENT", "kitchen-base")

#In this pattern, sc schema validation happens in chef.py when the SousChefRecipe is constructed.
#Therefore we just accept those parameters as a dict, and trust that it's correct. 
@flow(name=PREFECT_DEPLOYMENT)
async def kitchen_base(recipe_name: str, tags: List[str] = [], parameters:Dict = {}) -> FlowRun:
    tags += BASE_TAGS + [recipe_name]

    with prefect.tags(*tags):
        run_data = RunPipeline(parameters)

    # TODO: add task to cleanup return value (extract full_text)
    # TODO: add task to create_table_artifact from rundata after cleanup

    return run_data
