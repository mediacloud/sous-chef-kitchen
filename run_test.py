from flow import SousChefBaseOrder
from prefect_client import SousChefClient
import yaml
import asyncio


async def main():

	dep = yaml.safe_load(open("prefect.yaml").read())
	deployment_name = dep["deployments"][0]["name"]
	print(deployment_name)

	deployment_client = SousChefClient(deployment_name)

	order = SousChefBaseOrder(
		QUERY="northampton massachusetts",
		S3_PREFIX="first_buffet_test"
		)

	await deployment_client.run_deployment(parameters={"data":order.json()})

if __name__ == "__main__":
	loop = asyncio.get_event_loop()
	loop.run_until_complete(main())