import asyncio
from temporalio.client import Client
from temporalio.worker import Worker
from config import settings
from workflows.shipping_workflow import ShippingWorkflow
from  import (
    package_prepared,
    carrier_dispatched,
    order_shipped,
)

async def main():
    client = await Client.connect(settings.temporal_address) 
    worker = Worker(
        client,
        task_queue=settings.order_tq,
        workflows=[ShippingWorkflow],  
        activities=[package_prepared, carrier_dispatched, order_shipped],  # activities logic here
    )
    print("Shipping Worker is starting...")
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())