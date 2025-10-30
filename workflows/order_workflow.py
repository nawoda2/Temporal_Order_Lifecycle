from temporalio import workflow

@workflow.defn
class OrderWorkflow:
    def __init__(self):
        # Keep state in workflow fields; do not touch globals
        self._state = "INIT"
        self._errors: list[str] = []
        self._address: dict | None = None

    @workflow.run
    async def run(self, order_id: str, payment_id: str):
        # TODO: Implement orchestration:
        # ReceiveOrder -> ValidateOrder -> Timer -> Payment -> Child ShippingWorkflow
        # Use workflow.sleep, execute_activity, start_child_workflow
        raise NotImplementedError

    @workflow.signal
    def cancel_order(self):
        # TODO: Implement cancellation handling (scopes/propagation/compensation)
        pass

    @workflow.signal
    def update_address(self, address: dict):
        # TODO: Persist in workflow state and pass to shipping
        self._address = address

    @workflow.query
    def status(self) -> dict:
        # Return current, retries/errors, address, etc.
        return {"state": self._state, "address": self._address, "errors": list(self._errors)}