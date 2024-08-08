import prefect
from prefect.client.schemas.filters import (
    DeploymentFilter, DeploymentFilterName, FlowRunFilter, FlowRunFilterId, FlowRunFilterTags, 
    FlowRunFilterState, FlowRunFilterStateType,
    )
from prefect.client.schemas.objects import StateType
from prefect.blocks.system import Secret


def run_to_json(run):
    return {
        "id":run.id,
        "name":run.name,
        "parameters":run.parameters,
        "state_name":run.state_name,
        "state_type":run.state_type
    }


class SousChefClient():
    base_tags = ["buffet"]

    def __init__(self, tags=[]):
        self.base_tags += tags

        
    async def assert_prefect_connection(self):
        async with prefect.get_client() as client:
            response = await client.hello()
        return response.status_code == 200

    async def start_deployment(self, deployment_name, tags=[], parameters=None):
        tags = self.base_tags + tags
        deployment_filter = DeploymentFilter(
            name=DeploymentFilterName(any_=[deployment_name])  # Replace with your deployment name
        )

        matching_runs = await self.active_runs_with_tag(tags=tags)
        if len(matching_runs) > 0:
            raise RuntimeError("Won't launch while another run is still active")

        else:
            async with prefect.get_client() as client:
                response = await client.read_deployments(deployment_filter=deployment_filter)
                run = await client.create_flow_run_from_deployment(response[0].id, parameters=parameters, tags=self.tags)
                return run

    async def all_runs(self, tags=[]):
        tags = self.base_tags + tags
        tagged_filter = FlowRunFilter(
            tags=FlowRunFilterTags(all_=tags)
        )
        async with prefect.get_client() as client:
            matching_runs = await client.read_flow_runs(flow_run_filter=tagged_filter)
            return [run_to_json(r) for r in matching_runs]

    async def ongoing_runs(self, tags=[]):
        tags = self.base_tags + tags
        running_tagged_filter = FlowRunFilter(
            state=FlowRunFilterState(
                type=FlowRunFilterStateType(any_=[StateType.RUNNING, StateType.SCHEDULED,StateType.PENDING])),
            tags=FlowRunFilterTags(all_=tags)
        )
        async with prefect.get_client() as client:
            matching_runs = await client.read_flow_runs(flow_run_filter=running_tagged_filter)
            return matching_runs

    async def check_run_status(self, id):
        async with prefect.get_client() as client:
            value = await client.read_flow_run(id)
            return value

    async def check_secret_exists(self, secret_key) -> bool:
         async with prefect.get_client() as client:
            
            existing_secrets = await client.read_block_documents()
            existing_secret_names = [block.name for block in existing_secrets]
            if secret_key in existing_secret_names:
                return True
            return False

    async def get_or_create_secret(self, secret_key, secret_value):
        async with prefect.get_client() as client:

            if await self.check_secret_exists(secret_key):
                return secret_key
            else:
                # Create the Secret block
                secret_block = Secret(name=secret_key, value=secret_value)
                # Save the Secret block to Prefect with a name
                await secret_block.save(name=secret_key)
                
                return secret_key


    #get_status
    #get_artifacts

