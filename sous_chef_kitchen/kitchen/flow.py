"""
Run (cook) recipe requests on Prefect using the kitchen-base flow.
"""

import os
from typing import Dict, List

import prefect
from prefect import flow
from prefect.client.schemas.objects import FlowRun

from sous_chef import RunPipeline, recipe_loader
from sous_chef_kitchen.kitchen.models import SousChefBaseOrder
from sous_chef_kitchen.shared.recipe import get_recipe_folder

BASE_TAGS = ["kitchen"]
PREFECT_DEPLOYMENT = os.getenv("SC_PREFECT_DEPLOYMENT", "kitchen-base")


@flow(name=PREFECT_DEPLOYMENT)
async def kitchen_base(recipe_name: str, tags:List[str]=[],
    parameters:SousChefBaseOrder=None) -> FlowRun:
    """Handle orders for the requested recipe from the Sous Chef kitchen."""

    # NOTE: Refactoring this after realizing it did not block extracting the
    # output from the QueryOnlineNews atom from the client side as well as
    # I thought it did. Purging the corresponding return values from RunPipeline
    # seems to work in most but not all cases.

    tags += BASE_TAGS + [recipe_name]
    recipe_folder = get_recipe_folder(recipe_name)
    with open(f"{recipe_folder}/recipe.yaml", "r") as f:
        recipe = f.read()
    
    # TODO: Per the original note on the SousChefBaseOrder class, add a data
    # validation step here before the data is passed through to RunPipeline
    conf = recipe_loader.t_yaml_to_conf(recipe, **parameters.model_dump())
    conf["name"] = parameters.NAME
    with prefect.tags(*tags):
        run_data = RunPipeline(conf)

    return run_data

    # TODO: Re-add QueryOnlineNews return value cleanup here
    # TODO: Re-add task to create_table_artifact from run_data here after cleanup