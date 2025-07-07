import asyncio
import time
import os
import httpx
from prefect import get_client
from prefect.server.schemas.actions import WorkPoolCreate
from prefect.blocks.system import Secret
from prefect_aws import AwsCredentials
from prefect_github import GitHubCredentials
from prefect_email import EmailServerCredentials
from prefect_docker import DockerRegistryCredentials
from pydantic_settings import BaseSettings


PREFECT_API_URL = "http://prefect-server:4200/api"
WORK_POOL_NAME = os.environ.get("WORK_POOL_NAME", "default-work-pool") #From an env-var

##Utilities to setup the prefect environment via docker-compose

async def ensure_work_pool():
    async with get_client() as client:
        pools = await client.read_work_pools()
        if any(p.name == WORK_POOL_NAME for p in pools):
            print(f"✅ Work pool '{WORK_POOL_NAME}' already exists.")
        else:
            print(f"➕ Creating work pool '{WORK_POOL_NAME}'...")
            work_pool = WorkPoolCreate(
                name = WORK_POOL_NAME,
                type="process")
            result =await client.create_work_pool(work_pool)
            print(result)



def wait_for_api():
    print("⏳ Waiting for Prefect API...")
    for _ in range(30):
        try:
            r = httpx.get(f"{PREFECT_API_URL}/health", timeout=2)
            if r.status_code == 200 and r.text == "true":
                print("✅ Prefect API is ready.")
                return
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError("Prefect API did not become healthy in time.")


class SousChefCredentials(BaseSettings):

    ACCESS_KEY_ID:str
    ACCESS_KEY_SECRET:str

    #DOCKER_USERNAME:str
    #DOCKER_PASSWORD:str

    GMAIL_APP_USERNAME:str
    GMAIL_APP_PASSWORD:str

    #GITHUB_RO_PAT:str

    MEDIACLOUD_API_KEY:str

def setup_secrets(overwrite=True):
    print("⏳ Waiting for Prefect Secret setup_secrets...")
    config = SousChefCredentials()


    AwsCredentials(
        aws_access_key_id=config.ACCESS_KEY_ID,
        aws_secret_access_key=config.ACCESS_KEY_SECRET
        ).save("aws-s3-credentials", overwrite=overwrite)


    #DockerRegistryCredentials(
    #    username=config.DOCKER_USERNAME,
    #    password=config.DOCKER_PASSWORD,
    #    registry_url="index.docker.io" #I think this is only ever hardcoded
    #    ).save("docker-auth", overwrite=overwrite)


    #GitHubCredentials(token=config.GITHUB_RO_PAT
    #    ).save("sous-chef-read-only", overwrite=overwrite)


    EmailServerCredentials(
        username=config.GMAIL_APP_USERNAME,
        password=config.GMAIL_APP_PASSWORD
        ).save("email-password", overwrite=overwrite)


    Secret(value=config.MEDIACLOUD_API_KEY
        ).save("mediacloud-api-key", overwrite=overwrite)
    print("✅ Prefect Sous-Chef Secrets Setup")

if __name__ == "__main__":
    wait_for_api()
    asyncio.run(ensure_work_pool())
    setup_secrets()

