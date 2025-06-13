"""
Run (cook) recipe requests on Prefect using the kitchen-base flow.
"""

import os
import re
from typing import Dict, List

import prefect
from prefect import flow, get_run_logger, task
from prefect.artifacts import create_table_artifact
from prefect.client.schemas.objects import FlowRun
from prefect.context import FlowRunContext
from sous_chef import RunPipeline, SousChefRecipe

from sous_chef_kitchen.shared.recipe import get_recipe_folder

BASE_TAGS = ["kitchen"]
PREFECT_DEPLOYMENT = os.getenv("SC_PREFECT_DEPLOYMENT", "kitchen-base")


# In this pattern, sc schema validation happens in chef.py when the SousChefRecipe is constructed.
# Therefore we just accept those parameters as a dict, and trust that it's correct.
@flow(name=PREFECT_DEPLOYMENT)
def kitchen_base(
    recipe_name: str,
    tags: List[str] = [],
    parameters: Dict = {},
    return_restricted_artifacts: bool = False,
) -> FlowRun:
    logger = get_run_logger()
    tags += BASE_TAGS + [recipe_name]

    recipe_folder = get_recipe_folder(recipe_name)
    recipe_location = os.path.join(recipe_folder, "recipe.yaml")

    with prefect.tags(*tags):
        logger.info("Starting Sous-Chef Pipeline")
        run_data = RunPipeline(SousChefRecipe(recipe_location, parameters))

    flow_run_name = FlowRunContext.get().flow_run.dict().get("name")

    # create_table_artifact(key=flow_run_name, table=[run_data])

    for _task, output in run_data.items():
        key = re.sub("[^0-9a-zA-Z]+", "-", task.lower())

        if len(output) > 1:
            if output["restricted"] and not return_restricted_artifacts:
                pass

            else:
                create_table_artifact(
                    key=flow_run_name + "-" + key, table=[output], description=task
                )

    return run_data
