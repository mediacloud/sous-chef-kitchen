import asyncio
import pathlib
import time
import os
import httpx
from prefect import get_client
from prefect.server.schemas.actions import WorkPoolCreate
from sous_chef.scripts.setup_secrets import setup_secret_blocks

PREFECT_API_URL = "http://prefect-server:4200/api"
WORK_POOL_NAME = os.environ("WORK_POOL_NAME", "default-work-pool") #From an env-var

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


def setup_secrets():
    #Have to get the secret values from the environment...
    setup_secret_blocks()

if __name__ == "__main__":
    wait_for_api()
    asyncio.run(ensure_work_pool())

