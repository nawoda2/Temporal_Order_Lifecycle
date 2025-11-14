import asyncio, random, json, logging, uuid
from typing import Dict, Any
from db.session import get_db_pool

logger = logging.getLogger(__name__)

async def flaky_call() -> None:
    """Either raise an error or sleep long enough to trigger an activity timeout."""
    rand_num = random.random()
    if rand_num < 0.33:
        raise RuntimeError("Forced failure for testing")

    if rand_num < 0.67:
        await asyncio.sleep(300)  # Expect the activity layer to time out before this completes
        

async def order_received(order: Dict[str, Any]) -> Dict[str, Any]:
    await flaky_call()

    order_id = order.get("order_id")
    items = order.get("items", [])
    address = order.get("address")

    logger.info(f"Order {order_id} received with items={items} and address={address}")

    pool = await get_db_pool()
    async with pool.acquire() as conn:

        existing_order = await conn.fetchrow(
            "SELECT id, state, items_json, address_json FROM orders WHERE id = $1",
            order_id
        )
        
        if existing_order:
            logger.info(f"Order {order_id} already exists")
            return {
                "order_id": order_id,
                "items": json.loads(existing_order['items_json']) if existing_order['items_json'] else items,
                "address": json.loads(existing_order['address_json']) if existing_order['address_json'] else address
            }

        await conn.execute("""
            INSERT INTO orders (id, state, items_json, address_json, created_at, updated_at) 
            VALUES ($1, $2, $3, $4, NOW(), NOW())
            ON CONFLICT (id) DO NOTHING
        """,
        order_id,
        "ORDER_RECEIVED",
        json.dumps(items),
        json.dumps(address) if address else None
        )

        await conn.execute("""
            INSERT INTO events (id, order_id, type, payload_json, timestamp)
            VALUES ($1, $2, $3, $4, NOW())
        """,
        str(uuid.uuid4()),
        order_id,
        "ORDER_RECEIVED",
        json.dumps({"items": items, "address": address, "state": "ORDER_RECEIVED"})
        )

        logger.info(f"Order {order_id} successfully received and persisted to DB")

    return {"order_id": order_id, "items": items, "address": address}

async def order_validated(order: Dict[str, Any]) -> bool:
    await flaky_call()

    order_id = order.get("order_id")
    items = order.get("items", [])

    if not items:
        raise ValueError("No items to validate")

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        existing_order = await conn.fetchrow(
            "SELECT id, state, items_json, address_json FROM orders WHERE id = $1",
            order_id
        )

        if not existing_order:
            logger.error(f"Order {order_id} not found")
            raise ValueError(f"Order {order_id} not found")

        if existing_order['state'] == "ORDER_VALIDATED":
            logger.info(f"Order {order_id} already validated")
            return True
        await conn.execute("""
            UPDATE orders SET state = $1, updated_at = NOW() WHERE id = $2
            """,
            "ORDER_VALIDATED",
            order_id
        )

        await conn.execute("""
            INSERT INTO events (id, order_id, type, payload_json, timestamp)
            VALUES ($1, $2, $3, $4, NOW())
        """,
        str(uuid.uuid4()),
        order_id,
        "ORDER_VALIDATED",
        json.dumps({
            "state": "ORDER_VALIDATED",
            "previous_state": existing_order['state']
        })
        )

        logger.info(f"Order {order_id} successfully validated")

    return True

async def payment_charged(order: Dict[str, Any], payment_id: str, db) -> Dict[str, Any]:
    """Charge payment after simulating an error/timeout first.
    You must implement your own idempotency logic in the activity or here.
    """
    await flaky_call()
    
    order_id = order.get("order_id")

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        existing_payment = await conn.fetchrow(
            "SELECT payment_id, order_id, status, amount FROM payments WHERE payment_id = $1",
            payment_id
        )

        if existing_payment:
            logger.info(f"Payment {payment_id} already charged")
            return {
                "payment_id": payment_id,
                "order_id": order_id,
                "status": existing_payment['status'],
                "amount": float(existing_payment['amount'])
            }

        amount = sum(i.get("qty", 1) for i in order.get("items", []))

        await conn.execute("""
                INSERT INTO payments(payment_id, order_id, status, amount, created_at)
                VALUES ($1, $2, $3, $4, NOW())
                ON CONFLICT (payment_id) DO NOTHING
            """,
            payment_id,
            order_id,
            "CHARGED",
            amount
            )
        await conn.execute("""
            UPDATE orders SET state = $1, updated_at = NOW() WHERE id = $2
            """,
            "PAYMENT_CHARGED",
            order_id
        )

        await conn.execute("""
            INSERT INTO events (id, order_id, type, payload_json, timestamp)
            VALUES ($1, $2, $3, $4, NOW())
        """,
        str(uuid.uuid4()),
        order_id,
        "PAYMENT_CHARGED",
        json.dumps({
            "payment_id": payment_id,
            "amount": amount,
            "status": "PAYMENT_CHARGED"
        })
        )

        logger.info(f"Payment {payment_id} successfully charged")

    return {
        "payment_id": payment_id,
        "order_id": order_id,
        "status": "CHARGED", 
        "amount": amount
        }

async def order_shipped(order: Dict[str, Any]) -> str:
    await flaky_call()
    
    order_id = order.get("order_id")
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        existing_order = await conn.fetchrow(
            "SELECT id, state, items_json, address_json FROM orders WHERE id = $1",
            order_id
        )

        if not existing_order:
            logger.error(f"Order {order_id} not found")
            raise ValueError(f"Order {order_id} not found")
        
        if existing_order['state'] == "ORDER_SHIPPED":
            logger.info(f"Order {order_id} already shipped")
            return "ORDER_SHIPPED"
        
        await conn.execute("""
            UPDATE orders SET state = $1, updated_at = NOW() WHERE id = $2
            """,
            "ORDER_SHIPPED",
            order_id
        )

        await conn.execute("""
            INSERT INTO events (id, order_id, type, payload_json, timestamp)
            VALUES ($1, $2, $3, $4, NOW())
            """,
            str(uuid.uuid4()),
            order_id,
            "ORDER_SHIPPED",
            json.dumps({
                "state": "ORDER_SHIPPED",
                "previous_state": existing_order['state']
            })
        )

        logger.info(f"Order {order_id} successfully shipped")

    return "ORDER_SHIPPED"

async def package_prepared(order: Dict[str, Any]) -> str:
    await flaky_call()
    
    order_id = order.get("order_id")
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        existing_order = await conn.fetchrow(
            "SELECT id, state, items_json, address_json FROM orders WHERE id = $1",
            order_id
        )

        if not existing_order:
            logger.error(f"Order {order_id} not found")
            raise ValueError(f"Order {order_id} not found")

        if existing_order['state'] == "PACKAGE_PREPARED":
            logger.info(f"Order {order_id} already prepared")
            return "PACKAGE_PREPARED"

        await conn.execute("""
            UPDATE orders SET state = $1, updated_at = NOW() WHERE id = $2
            """,
            "PACKAGE_PREPARED",
            order_id
        )

        await conn.execute("""
            INSERT INTO events (id, order_id, type, payload_json, timestamp)
            VALUES ($1, $2, $3, $4, NOW())
            """,
            str(uuid.uuid4()),
            order_id,
            "PACKAGE_PREPARED",
            json.dumps({
                "state": "PACKAGE_PREPARED",
                "previous_state": existing_order['state']
            })
        )

        logger.info(f"Order {order_id} successfully prepared")

    return "PACKAGE_PREPARED"

async def carrier_dispatched(order: Dict[str, Any]) -> str:
    await flaky_call()
    
    order_id = order.get("order_id")
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        existing_order = await conn.fetchrow(
            "SELECT id, state, items_json, address_json FROM orders WHERE id = $1",
            order_id
        )

        if not existing_order:
            logger.error(f"Order {order_id} not found")
            raise ValueError(f"Order {order_id} not found")
        
        if existing_order['state'] == "CARRIER_DISPATCHED":
            logger.info(f"Order {order_id} already dispatched")
            return "CARRIER_DISPATCHED"
        
        await conn.execute("""
            UPDATE orders SET state = $1, updated_at = NOW() WHERE id = $2
            """,
            "CARRIER_DISPATCHED",
            order_id
        )

        await conn.execute("""
            INSERT INTO events (id, order_id, type, payload_json, timestamp)
            VALUES ($1, $2, $3, $4, NOW())
            """,
            str(uuid.uuid4()),
            order_id,
            "CARRIER_DISPATCHED",
            json.dumps({
                "state": "CARRIER_DISPATCHED",
                "previous_state": existing_order['state']
            })
        )

        logger.info(f"Order {order_id} successfully dispatched")

    return "CARRIER_DISPATCHED"

async def update_order_address(order_id: str, address: dict) -> None:
    await flaky_call()
    
    logger.info(f"Updating address for order {order_id}")
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        existing_order = await conn.fetchrow(
            "SELECT id, address_json FROM orders WHERE id = $1",
            order_id
        )
        
        if not existing_order:
            logger.error(f"Order {order_id} not found")
            raise ValueError(f"Order {order_id} not found")
        
        old_address = json.loads(existing_order['address_json']) if existing_order['address_json'] else None
        
        await conn.execute("""
            UPDATE orders SET address_json = $1, updated_at = NOW() WHERE id = $2
        """,
        json.dumps(address),
        order_id
        )
        
        await conn.execute("""
            INSERT INTO events (id, order_id, type, payload_json, timestamp)
            VALUES ($1, $2, $3, $4, NOW())
        """,
        str(uuid.uuid4()),
        order_id,
        "ADDRESS_UPDATED",
        json.dumps({
            "old_address": old_address,
            "new_address": address
        })
        )
    
    logger.info(f"Address updated for order {order_id}")
