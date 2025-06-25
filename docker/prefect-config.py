import asyncio
import time
import httpx
from prefect import get_client
from prefect.client.exceptions import ObjectNotFound

PREFECT_API_URL = "http://prefect-server:4200/api"
WORK_POOL_NAME = "default-agent-pool"


async def ensure_work_pool():
    async with get_client() as client:
        try:
            await client.read_work_pool(WORK_POOL_NAME)
            print(f"✅ Work pool '{WORK_POOL_NAME}' already exists.")
        except ObjectNotFound:
            print(f"➕ Creating work pool '{WORK_POOL_NAME}'...")
            await client.create_work_pool(name=WORK_POOL_NAME, type="process")


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


if __name__ == "__main__":
    wait_for_api()
    asyncio.run(ensure_work_pool())
