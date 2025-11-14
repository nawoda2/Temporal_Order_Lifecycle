from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta
from typing import Dict, Any

with workflow.unsafe.imports_passed_through():
    from activities.activities import (
        order_received,
        order_validated,
        payment_charged,
        order_shipped,
        update_order_address,
    )
    from config import settings

STANDARD_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(milliseconds=5),
    maximum_interval=timedelta(milliseconds=200),
    backoff_coefficient=1.0,
    maximum_attempts=1000,
)

STANDARD_TIMEOUT = timedelta(seconds=2)

@workflow.defn
class OrderWorkflow:
    def __init__(self):
        self._state = "INIT"
        self._errors: list[str] = []
        self._address: dict | None = None
        self._cancelled = False
        self._order_data: dict | None = None
        self._manual_review_approved = False

    @workflow.run
    async def run(self, order_id: str, payment_id: str, items: list[dict], address: dict = None) -> Dict[str, Any]:
        try:
            self._state = "RECEIVING"
            self._address = address
            
            workflow.logger.info(f"Starting OrderWorkflow for {order_id}")
            order_data = {
                "order_id": order_id,
                "items": items,
                "address": self._address
            }
            
            order_result = await workflow.execute_activity(
                order_received,
                order_data,
                start_to_close_timeout=STANDARD_TIMEOUT,
                retry_policy=STANDARD_RETRY_POLICY,
            )
            
            self._order_data = order_result
            workflow.logger.info(f"Order {order_id} received")
            
            if self._cancelled:
                self._state = "CANCELLED"
                workflow.logger.info(f"Order {order_id} cancelled after receiving")
                return {"status": "cancelled", "order_id": order_id}
            
            self._state = "VALIDATING"
            workflow.logger.info(f"Validating order {order_id}")
            
            validation_result = await workflow.execute_activity(
                order_validated,
                self._order_data,
                start_to_close_timeout=STANDARD_TIMEOUT,
                retry_policy=STANDARD_RETRY_POLICY,
            )
            
            workflow.logger.info(f"Order {order_id} validated: {validation_result}")
            
            if self._cancelled:
                self._state = "CANCELLED"
                workflow.logger.info(f"Order {order_id} cancelled after validation")
                return {"status": "cancelled", "order_id": order_id}
            
            self._state = "AWAITING_APPROVAL"
            workflow.logger.info(f"Order {order_id} awaiting manual approval")
            
            await workflow.wait_condition(
                lambda: self._manual_review_approved or self._cancelled,
                timeout=timedelta(seconds=300)
            )
            
            if self._cancelled:
                self._state = "CANCELLED"
                workflow.logger.info(f"Order {order_id} cancelled during manual review")
                return {"status": "cancelled", "order_id": order_id}
            
            if not self._manual_review_approved:
                self._state = "APPROVAL_TIMEOUT"
                workflow.logger.error(f"Order {order_id} manual approval timeout")
                raise TimeoutError("Manual approval not received within timeout period")
            
            workflow.logger.info(f"Order {order_id} manually approved")
            
            self._state = "CHARGING_PAYMENT"
            workflow.logger.info(f"Charging payment for order {order_id}")
            
            self._order_data["address"] = self._address
            
            payment_result = await workflow.execute_activity(
                payment_charged,
                args=[self._order_data, payment_id],
                start_to_close_timeout=STANDARD_TIMEOUT,
                retry_policy=STANDARD_RETRY_POLICY,
            )
            
            workflow.logger.info(f"Payment charged for order {order_id}: {payment_result}")
            
            self._state = "SHIPPING"
            workflow.logger.info(f"Starting shipping workflow for order {order_id}")
            
            from workflows.shipping_workflow import ShippingWorkflow
            
            shipping_handle = await workflow.start_child_workflow(
                ShippingWorkflow.run,
                self._order_data,
                id=f"shipping-{order_id}",
                task_queue=settings.shipping_tq,
            )
            
            shipping_result = await shipping_handle
            workflow.logger.info(f"Shipping completed for order {order_id}: {shipping_result}")
            
            self._state = "SHIPPED"
            await workflow.execute_activity(
                order_shipped,
                self._order_data,
                start_to_close_timeout=STANDARD_TIMEOUT,
                retry_policy=STANDARD_RETRY_POLICY,
            )
            
            self._state = "COMPLETED"
            workflow.logger.info(f"Order {order_id} workflow completed")
            
            return {
                "status": "completed",
                "order_id": order_id,
                "payment": payment_result,
                "shipping": shipping_result,
            }
            
        except Exception as e:
            self._state = "FAILED"
            error_msg = f"Workflow failed: {str(e)}"
            self._errors.append(error_msg)
            workflow.logger.error(f"Order {order_id} workflow failed: {e}")
            raise

    @workflow.signal
    async def cancel_order(self):
        workflow.logger.info(f"Cancel signal received, current state: {self._state}")
        if self._state in ["INIT", "RECEIVING", "VALIDATING", "AWAITING_APPROVAL"]:
            self._cancelled = True
            workflow.logger.info("Order marked for cancellation")
        else:
            workflow.logger.warning(f"Cannot cancel order in state: {self._state}")

    @workflow.signal
    async def update_address(self, address: dict):
        workflow.logger.info(f"Address update signal received: {address}")
        self._address = address
        if self._order_data:
            self._order_data["address"] = address
            
            try:
                await workflow.execute_activity(
                    update_order_address,
                    args=[self._order_data["order_id"], address],
                    start_to_close_timeout=STANDARD_TIMEOUT,
                    retry_policy=STANDARD_RETRY_POLICY,
                )
                workflow.logger.info("Address updated in DB")
            except Exception as e:
                workflow.logger.error(f"Failed to update address in DB: {e}")
                self._errors.append(f"Address update failed: {str(e)}")
        else:
            workflow.logger.info("Address updated in workflow state (order not yet created)")

    @workflow.signal
    async def approve_order(self):
        workflow.logger.info("Manual approval signal received")
        self._manual_review_approved = True

    @workflow.signal
    async def dispatch_failed(self, reason: str):
        workflow.logger.error(f"Dispatch failed signal received: {reason}")
        self._errors.append(f"Dispatch failed: {reason}")

    @workflow.query
    def status(self) -> dict:
        return {
            "state": self._state,
            "address": self._address,
            "errors": list(self._errors),
            "cancelled": self._cancelled,
            "manual_review_approved": self._manual_review_approved,
        }
