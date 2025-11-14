import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from temporalio.client import Client
from workflows.order_workflow import OrderWorkflow
from config import settings
import uuid

async def main():
    client = await Client.connect(settings.temporal_address)
    
    order_id = f"order-{uuid.uuid4().hex[:8]}"
    payment_id = f"pay-{uuid.uuid4().hex[:8]}"
    
    print(f"\nStarting order workflow: {order_id}")
    print(f"Payment ID: {payment_id}")
    
    handle = await client.start_workflow(
        OrderWorkflow.run,
        args=[
            order_id,
            payment_id,
            [{"sku": "WIDGET-A", "qty": 2}, {"sku": "GADGET-B", "qty": 1}],
            {"street": "123 Main St", "city": "NYC", "zip": "10001"}
        ],
        id=order_id,
        task_queue=settings.order_tq,
    )
    
    print(f"\nWorkflow started! Workflow ID: {order_id}")
    print(f"Run ID: {handle.first_execution_run_id}")
    
    print("\nWaiting for order to reach AWAITING_APPROVAL state...")
    
    max_attempts = 30
    for attempt in range(max_attempts):
        try:
            status = await handle.query(OrderWorkflow.status)
            print(f"Current state: {status['state']}", end="\r")
            
            if status['state'] == 'AWAITING_APPROVAL':
                print("\n")
                break
            elif status['state'] in ['COMPLETED', 'FAILED', 'CANCELLED']:
                print(f"\n\nWorkflow already in terminal state: {status['state']}")
                print(f"Final status: {status}")
                return
                
            await asyncio.sleep(1)
        except Exception as e:
            print(f"\nError querying workflow: {e}")
            await asyncio.sleep(1)
    else:
        print(f"\n\nTimeout: Workflow did not reach AWAITING_APPROVAL state after {max_attempts} seconds")
        status = await handle.query(OrderWorkflow.status)
        print(f"Current status: {status}")
        return
    
    print("="*60)
    print("ORDER NEEDS MANUAL APPROVAL!")
    print("="*60)
    print(f"\nOption 1: Use API")
    print(f'  curl.exe -X POST "http://localhost:8000/orders/{order_id}/signals/approve"')
    print(f"\nOption 2: Use Temporal CLI")
    print(f'  temporal workflow signal --workflow-id {order_id} --name approve_order')
    print(f"\nOption 3: Press Enter to approve now...")
    print("="*60)
    
    input()
    
    print("\nSending approval signal...")
    await handle.signal(OrderWorkflow.approve_order)
    print("Approval sent!")
    
    print(f"\nWaiting for workflow to complete...")
    print("You can check the Temporal UI at: http://localhost:8233")
    print(f"Workflow will complete in ~15 seconds (with retries)")
    
    try:
        result = await handle.result()
        print(f"\n✓ Workflow completed successfully!")
        print(f"Result: {result}")
    except Exception as e:
        print(f"\n✗ Workflow failed: {e}")
        status = await handle.query(OrderWorkflow.status)
        print(f"Final status: {status}")

if __name__ == "__main__":
    asyncio.run(main())

