from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta
from typing import Dict, Any

with workflow.unsafe.imports_passed_through():
    from activities.activities import (
        package_prepared,
        carrier_dispatched,
    )

STANDARD_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(milliseconds=5),
    maximum_interval=timedelta(milliseconds=200),
    backoff_coefficient=1.0,
    maximum_attempts=1000,
)

STANDARD_TIMEOUT = timedelta(seconds=2)

@workflow.defn
class ShippingWorkflow:
    def __init__(self):
        self._state = "INIT"

    @workflow.run
    async def run(self, order: dict) -> Dict[str, Any]:
        order_id = order.get("order_id")
        
        try:
            self._state = "PREPARING"
            workflow.logger.info(f"Preparing package for order {order_id}")
            
            package_result = await workflow.execute_activity(
                package_prepared,
                order,
                start_to_close_timeout=STANDARD_TIMEOUT,
                retry_policy=STANDARD_RETRY_POLICY,
            )
            
            workflow.logger.info(f"Package prepared for order {order_id}: {package_result}")
            
            self._state = "DISPATCHING"
            workflow.logger.info(f"Dispatching carrier for order {order_id}")
            
            try:
                dispatch_result = await workflow.execute_activity(
                    carrier_dispatched,
                    order,
                    start_to_close_timeout=STANDARD_TIMEOUT,
                    retry_policy=STANDARD_RETRY_POLICY,
                )
                
                workflow.logger.info(f"Carrier dispatched for order {order_id}: {dispatch_result}")
                
                self._state = "DISPATCHED"
                return {
                    "status": "dispatched",
                    "order_id": order_id,
                    "package": package_result,
                    "dispatch": dispatch_result,
                }
                
            except Exception as dispatch_error:
                workflow.logger.error(f"Dispatch failed for order {order_id}: {dispatch_error}")
                
                parent_workflow_id = workflow.info().parent.workflow_id if workflow.info().parent else None
                
                if parent_workflow_id:
                    workflow.logger.info(f"Signaling parent workflow {parent_workflow_id} about dispatch failure")
                    from workflows.order_workflow import OrderWorkflow
                    
                    parent_handle = workflow.get_external_workflow_handle(parent_workflow_id)
                    await parent_handle.signal(OrderWorkflow.dispatch_failed, f"Carrier dispatch failed: {str(dispatch_error)}")
                
                raise
                
        except Exception as e:
            self._state = "FAILED"
            workflow.logger.error(f"Shipping workflow failed for order {order_id}: {e}")
            raise

    @workflow.query
    def status(self) -> dict:
        return {"state": self._state}
