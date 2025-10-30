from temporalio import activity
from typing import Any, Dict


from function_stubs import (
    order_received as _order_received,
    order_validated as _order_validated,
    payment_charged as _payment_charged,
    order_shipped as _order_shipped,
    package_prepared as _package_prepared,
    carrier_dispatched as _carrier_dispatched,
)

@activity.defn
async def order_received(order_id: str) -> Dict[str, Any]:
    return await _order_received(order_id)

@activity.defn
async def order_validated(order: Dict[str, Any]) -> bool:
    return await _order_validated(order)

@activity.defn
async def payment_charged(order: Dict[str, Any], payment_id: str) -> Dict[str, Any]:
    
    return await _payment_charged(order, payment_id, db=None)

@activity.defn
async def order_shipped(order: Dict[str, Any]) -> str:
    return await _order_shipped(order)

@activity.defn
async def package_prepared(order: Dict[str, Any]) -> str:
    return await _package_prepared(order)

@activity.defn
async def carrier_dispatched(order: Dict[str, Any]) -> str:
    return await _carrier_dispatched(order)