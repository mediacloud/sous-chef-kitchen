import prefect
from prefect.client.schemas.filters import (
    DeploymentFilter, DeploymentFilterName, FlowRunFilter, FlowRunFilterId, FlowRunFilterTags, 
    FlowRunFilterState, FlowRunFilterStateType,
    )
from prefect.client.schemas.objects import StateType


class SousChefClient():
    base_tags = ["buffet"]

    def __init__(self, deployment_name):
        self.deployment_name = deployment_name

        #connected = await self.assert_prefect_connection()
        #if not connected:
        #    raise RuntimeError("cannot establish connection to prefect service")

    async def assert_prefect_connection(self):
        async with prefect.get_client() as client:
            response = await client.hello()
        return response.status_code == 200


    async def run_deployment(self, tags=[], parameters=None):

        tags = self.base_tags + tags

        running_tagged_filter = FlowRunFilter(
            state=FlowRunFilterState(
                type=FlowRunFilterStateType(any_=[StateType.RUNNING, StateType.SCHEDULED,StateType.PENDING])),
            tags=FlowRunFilterTags(all_=tags)
        )

        deployment_filter = DeploymentFilter(
            name=DeploymentFilterName(any_=[self.deployment_name])  # Replace with your deployment name
        )

        async with prefect.get_client() as client:

            matching_runs = await client.read_flow_runs(flow_run_filter=running_tagged_filter)
            
            if len(matching_runs) <= 0:
                print(parameters)
                response = await client.read_deployments(deployment_filter=deployment_filter)
                run = await client.create_flow_run_from_deployment(response[0].id, parameters=parameters, tags=tags)
                return run
            else:
                raise RuntimeError("Won't launch while another run is still active")
            #This should also set the id on this object so we can check against it later. 

    #get_active_flows
    #get_status
    #get_artifacts

