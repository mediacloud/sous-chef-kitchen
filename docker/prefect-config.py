import asyncio
import os
import time

import httpx
from dotenv import load_dotenv
from prefect import get_client
from prefect.blocks.system import Secret
from prefect.server.schemas.actions import WorkPoolCreate
from prefect_aws import AwsClientParameters, AwsCredentials
from prefect_email import EmailServerCredentials
from pydantic_settings import BaseSettings

load_dotenv()

PREFECT_API_URL = os.environ.get("PREFECT_API_URL", "http://prefect-server:4200/api")
WORK_POOL_NAME = os.environ.get(
    "WORK_POOL_NAME", "default-work-pool"
)  # From an env-var

# Utilities to setup the prefect environment via docker-compose


async def ensure_work_pool():
    async with get_client() as client:
        pools = await client.read_work_pools()
        if any(p.name == WORK_POOL_NAME for p in pools):
            print(f"✅ Work pool '{WORK_POOL_NAME}' already exists.")
        else:
            print(f"➕ Creating work pool '{WORK_POOL_NAME}'...")
            work_pool = WorkPoolCreate(name=WORK_POOL_NAME, type="process")
            result = await client.create_work_pool(work_pool)
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

    # ACCESS_KEY_ID: str
    # ACCESS_KEY_SECRET: str

    B2_S3_ENDPOINT: str
    B2_KEY_ID: str
    B2_APP_KEY: str

    GMAIL_APP_USERNAME: str
    GMAIL_APP_PASSWORD: str

    MEDIACLOUD_API_KEY: str


def setup_secrets(overwrite=True):
    print("⏳ Waiting for Prefect Secret setup_secrets...")
    config = SousChefCredentials()

    def strip_quotes(value: str) -> str:
        """Strip surrounding quotes from environment variable values."""
        if isinstance(value, str) and len(value) >= 2:
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                return value[1:-1]
        return value

    # AwsCredentials(
    #    aws_access_key_id=config.ACCESS_KEY_ID,
    #    aws_secret_access_key=config.ACCESS_KEY_SECRET,
    # ).save("aws-s3-credentials", overwrite=overwrite)

    print("Setting up B2 with the following credentials:")
    print(
        f"KEY_ID: {config.B2_KEY_ID}, APP_KEY: {config.B2_APP_KEY}, endpoint: {config.B2_S3_ENDPOINT}"
    )
    AwsCredentials(
        aws_access_key_id=config.B2_KEY_ID,
        aws_secret_access_key=config.B2_APP_KEY,
        aws_client_parameters=AwsClientParameters(endpoint_url=config.B2_S3_ENDPOINT),
    ).save("b2-s3-credentials", overwrite=overwrite)

    EmailServerCredentials(
        username=config.GMAIL_APP_USERNAME,
        password=strip_quotes(config.GMAIL_APP_PASSWORD),
    ).save("email-password", overwrite=overwrite)

    Secret(value=config.MEDIACLOUD_API_KEY).save(
        "mediacloud-api-key", overwrite=overwrite
    )
    print("✅ Prefect Sous-Chef Secrets Setup")


if __name__ == "__main__":
    wait_for_api()
    asyncio.run(ensure_work_pool())
    setup_secrets()
