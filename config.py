from pydantic import BaseModel
import os

class Settings(BaseModel):
    temporal_address: str = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    order_tq: str = os.getenv("ORDER_TASK_QUEUE", "order-tq")
    shipping_tq: str = os.getenv("SHIPPING_TASK_QUEUE", "shipping-tq")
    database_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://temporal:temporal@localhost:5432/orders")

settings = Settings()