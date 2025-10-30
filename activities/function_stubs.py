import asyncio, random
from typing import Dict, Any

async def flaky_call() -> None:
    """Either raise an error or sleep long enough to trigger an activity timeout."""
    rand_num = random.random()
    if rand_num < 0.33:
        raise RuntimeError("Forced failure for testing")

    if rand_num < 0.67:
        await asyncio.sleep(300)  # Expect the activity layer to time out before this completes
        

async def order_received(order_id: str) -> Dict[str, Any]:
    await flaky_call()
    # TODO: Implement DB write: insert new order record
    return {"order_id": order_id, "items": [{"sku": "ABC", "qty": 1}]}

async def order_validated(order: Dict[str, Any]) -> bool:
    await flaky_call()
    # TODO: Implement DB read/write: fetch order, update validation status
    if not order.get("items"):
        raise ValueError("No items to validate")
    return True

async def payment_charged(order: Dict[str, Any], payment_id: str, db) -> Dict[str, Any]:
    """Charge payment after simulating an error/timeout first.
    You must implement your own idempotency logic in the activity or here.
    """
    await flaky_call()
    # TODO: Implement DB read/write: check payment record, insert/update payment status
    amount = sum(i.get("qty", 1) for i in order.get("items", []))
    return {"status": "charged", "amount": amount}

async def order_shipped(order: Dict[str, Any]) -> str:
    await flaky_call()
    # TODO: Implement DB write: update order status to shipped
    return "Shipped"

async def package_prepared(order: Dict[str, Any]) -> str:
    await flaky_call()
    # TODO: Implement DB write: mark package prepared in DB
    return "Package ready"

async def carrier_dispatched(order: Dict[str, Any]) -> str:
    await flaky_call()
    # TODO: Implement DB write: record carrier dispatch status
    return "Dispatched"
