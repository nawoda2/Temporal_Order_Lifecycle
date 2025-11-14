import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from temporalio.client import Client
from temporalio.worker import Worker
from config import settings
from workflows.order_workflow import OrderWorkflow
from activities.activities import (
    order_received,
    order_validated,
    payment_charged,
    order_shipped,
    update_order_address,
)
from db.session import init_db_pool, init_schema

async def main():
    await init_db_pool()
    await init_schema()

    print("Database initialized")

    
    client = await Client.connect(settings.temporal_address) # connection to temporal server so localhost:7233
    worker = Worker(
        client,
        task_queue=settings.order_tq,
        workflows=[OrderWorkflow],  # workflows.order_workflow logic here
        activities=[order_received, order_validated, payment_charged, order_shipped, update_order_address],
    )
    print("Order Worker is starting...")
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())