import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from temporalio.client import Client
from typing import Optional, List, Dict, Any
from config import settings
from workflows.order_workflow import OrderWorkflow
import uuid
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.temporal_client = await Client.connect(settings.temporal_address)
    yield
    if hasattr(app.state, "temporal_client"):
        await app.state.temporal_client.close()

app = FastAPI(title="Temporal Order Lifecycle API", lifespan=lifespan)

class OrderRequest(BaseModel):
    payment_id: str
    items: List[Dict[str, Any]]
    address: Optional[Dict[str, str]] = None

class AddressUpdate(BaseModel):
    address: Dict[str, str]

@app.post("/orders/{order_id}/start")
async def start_order_workflow(order_id: str, request: OrderRequest):
    client: Client = app.state.temporal_client
    
    try:
        handle = await client.start_workflow(
            OrderWorkflow.run,
            args=[order_id, request.payment_id, request.items, request.address],
            id=order_id,
            task_queue=settings.order_tq,
        )
        return {
            "status": "started",
            "workflow_id": order_id,
            "payment_id": request.payment_id,
            "run_id": handle.first_execution_run_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/orders/{order_id}/signals/cancel")
async def cancel_order(order_id: str):
    client: Client = app.state.temporal_client
    
    try:
        handle = client.get_workflow_handle(order_id)
        await handle.signal(OrderWorkflow.cancel_order)
        return {"status": "signal_sent", "signal": "cancel_order"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/orders/{order_id}/signals/update-address")
async def update_address(order_id: str, request: AddressUpdate):
    client: Client = app.state.temporal_client
    
    try:
        handle = client.get_workflow_handle(order_id)
        await handle.signal(OrderWorkflow.update_address, request.address)
        return {"status": "signal_sent", "signal": "update_address", "address": request.address}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/orders/{order_id}/signals/approve")
async def approve_order(order_id: str):
    client: Client = app.state.temporal_client
    
    try:
        handle = client.get_workflow_handle(order_id)
        await handle.signal(OrderWorkflow.approve_order)
        return {"status": "signal_sent", "signal": "approve_order"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/orders/{order_id}/status")
async def get_order_status(order_id: str):
    client: Client = app.state.temporal_client
    
    try:
        handle = client.get_workflow_handle(order_id)
        status = await handle.query(OrderWorkflow.status)
        
        workflow_description = await handle.describe()
        
        return {
            "workflow_id": order_id,
            "status": workflow_description.status.name,
            "workflow_state": status,
            "run_id": workflow_description.run_id,
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {str(e)}")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

