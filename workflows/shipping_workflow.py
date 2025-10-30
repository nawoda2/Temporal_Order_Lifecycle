from temporalio import workflow

@workflow.defn
class ShippingWorkflow:
    @workflow.run
    async def run(self, order: dict):
        # TODO: PreparePackage -> DispatchCarrier
        # On failure, signal parent (get_external_workflow_handle) and rethrow
        raise NotImplementedError