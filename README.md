# Temporal Order Lifecycle

Order processing system using Temporal workflows with retry logic, idempotency, and human-in-the-loop approval.

## Architecture

### Workflows
- **OrderWorkflow**: Main workflow handling order lifecycle (order-tq)
  - Steps: Receive → Validate → Manual Review → Payment → Shipping → Complete
  - Signals: cancel_order, update_address, approve_order
  - Query: status
  
- **ShippingWorkflow**: Child workflow for shipping (shipping-tq)
  - Steps: Prepare Package → Dispatch Carrier
  - Signals parent on dispatch failure

### Activities
- `order_received`: Insert order into DB
- `order_validated`: Validate order items
- `payment_charged`: Charge payment with idempotency
- `update_order_address`: Update shipping address in DB (called by signal)
- `package_prepared`: Prepare shipping package
- `carrier_dispatched`: Dispatch to carrier
- `order_shipped`: Mark order as shipped

### Database Schema

#### `orders` Table
Stores order records with state machine tracking.

| Column | Type | Description |
|--------|------|-------------|
| `id` | VARCHAR(255) | Primary key - order identifier |
| `state` | VARCHAR(255) | Current workflow state (e.g., `ORDER_RECEIVED`, `AWAITING_APPROVAL`, `COMPLETED`) |
| `items_json` | JSONB | Order line items as JSON array |
| `address_json` | JSONB | Shipping address as JSON object |
| `created_at` | TIMESTAMP | Order creation time |
| `updated_at` | TIMESTAMP | Last state update time |

**Indexes:**
- `idx_orders_state` on `state` - Fast filtering by order status

**States:**
- `ORDER_RECEIVED` → `ORDER_VALIDATED` → `AWAITING_APPROVAL` → `PAYMENT_CHARGED` → `SHIPPING` → `SHIPPED` → `COMPLETED`
- Error states: `FAILED`, `CANCELLED`, `APPROVAL_TIMEOUT`

#### `payments` Table
Payment records with idempotency via primary key.

| Column | Type | Description |
|--------|------|-------------|
| `payment_id` | VARCHAR(255) | Primary key - idempotency key to prevent double charges |
| `order_id` | VARCHAR(255) | Foreign key to orders |
| `status` | VARCHAR(255) | Payment status (`PENDING`, `COMPLETED`, `FAILED`) |
| `amount` | DECIMAL(10, 2) | Payment amount |
| `created_at` | TIMESTAMP | Payment processing time |

**Indexes:**
- `idx_payments_order_id` on `order_id` - Fast lookup of payments by order

**Idempotency:** 
- `payment_id` as PK ensures `INSERT ... ON CONFLICT DO NOTHING` prevents duplicate charges
- Activity checks for existing payment before calling `flaky_call()` to avoid charging on retry

#### `events` Table
Immutable audit log for all state transitions.

| Column | Type | Description |
|--------|------|-------------|
| `id` | VARCHAR(255) | Primary key - UUID for each event |
| `order_id` | VARCHAR(255) | Foreign key to orders |
| `type` | VARCHAR(255) | Event type (e.g., `ORDER_RECEIVED`, `PAYMENT_CHARGED`, `ADDRESS_UPDATED`) |
| `payload_json` | JSONB | Event-specific data (items, amounts, old/new values) |
| `timestamp` | TIMESTAMP | Event occurrence time |

**Indexes:**
- `idx_events_order_id` on `order_id` - Fast retrieval of order history
- `idx_events_timestamp` on `timestamp` - Chronological queries
- `idx_events_type` on `type` - Filter by event type

**Event Types:**
- `ORDER_RECEIVED` - Initial order creation
- `ORDER_VALIDATED` - Validation completed
- `PAYMENT_CHARGED` - Payment processed
- `ADDRESS_UPDATED` - Shipping address changed (via signal)
- `ORDER_SHIPPED` - Order dispatched
- `PACKAGE_PREPARED` - Package ready for shipping
- `CARRIER_DISPATCHED` - Carrier picked up package

**Example Event Payload:**
```json
{
  "payment_id": "pay-123",
  "amount": 59.98,
  "previous_status": "PENDING"
}
```

## Quick Start

### Start Everything

```bash
docker-compose up -d --build
```

This starts:
- Temporal Server (localhost:7233)
- Temporal UI (http://localhost:8233)
- PostgreSQL (localhost:5432)
- Order Worker (auto-creates DB & tables)
- Shipping Worker
- API Server (http://localhost:8000)

### Check Status

```bash
docker-compose ps
```

### View Logs

```bash
docker-compose logs -f order-worker
docker-compose logs -f shipping-worker
docker-compose logs -f api
```

## Usage

### API Examples

#### Start an Order Workflow

```bash
curl -X POST http://localhost:8000/orders/order-123/start \
  -H "Content-Type: application/json" \
  -d '{
    "payment_id": "pay-456",
    "items": [{"name": "Widget", "price": 29.99, "quantity": 2}],
    "address": {"street": "123 Main St", "city": "NYC", "zip": "10001"}
  }'
```

Or use the test file:
```bash
curl -X POST http://localhost:8000/orders/order-123/start \
  -H "Content-Type: application/json" \
  -d @test_order.json
```

#### Approve Order (Manual Review Step)

```bash
curl -X POST http://localhost:8000/orders/order-123/signals/approve
```

#### Update Shipping Address

```bash
curl -X POST http://localhost:8000/orders/order-123/signals/update-address \
  -H "Content-Type: application/json" \
  -d '{"address": {"street": "456 New Ave", "city": "LA", "zip": "90001"}}'
```

Or use the test file:
```bash
curl -X POST http://localhost:8000/orders/order-123/signals/update-address \
  -H "Content-Type: application/json" \
  -d @test_address.json
```

**Note:** The address is immediately updated in the database via the `update_order_address` activity, ensuring database consistency. The activity has retry logic to handle failures.

#### Cancel Order

```bash
curl -X POST http://localhost:8000/orders/order-123/signals/cancel
```

#### Check Order Status

```bash
curl http://localhost:8000/orders/order-123/status
```

## Testing

Run a complete workflow test:

```bash
python test_workflow.py
```

## Key Features

### Retry Logic
- All activities retry up to 1000 times 
- 2-second timeout per attempt to handle flaky_call() failures

### Idempotency
- Payment uses unique payment_id to prevent double charges
- All DB operations check for existing records before inserting
- Safe to retry any activity

### Manual Review
- Workflow pauses at AWAITING_APPROVAL state
- Requires approve_order signal to continue
- 5-minute timeout if no approval received

### Separate Task Queues
- OrderWorkflow runs on `order-tq`
- ShippingWorkflow runs on `shipping-tq`
- Allows independent scaling of workers

### Observability
- Structured logging throughout
- Event table for complete audit trail
- Query endpoints for live state inspection
- Temporal UI for visual workflow monitoring

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/orders/{id}/start` | Start order workflow |
| POST | `/orders/{id}/signals/approve` | Approve order |
| POST | `/orders/{id}/signals/cancel` | Cancel order |
| POST | `/orders/{id}/signals/update-address` | Update address |
| GET | `/orders/{id}/status` | Get order status |
| GET | `/health` | Health check |

## Project Structure

```
├── activities/
│   ├── activities.py        # Temporal activity definitions
│   └── function_stubs.py    # Business logic with flaky_call()
├── db/
│   ├── schema.sql           # Database schema
│   └── session.py           # DB connection pool
├── workflows/
│   ├── order_workflow.py    # Main order workflow
│   └── shipping_workflow.py # Shipping child workflow
├── worker/
│   ├── order_worker.py      # Order task queue worker
│   └── shipping_worker.py   # Shipping task queue worker
├── api.py                   # FastAPI REST API
├── config.py                # Configuration settings
├── docker-compose.yml       # Infrastructure setup
└── test_workflow.py         # End-to-end test
```

## Configuration

Environment variables (or defaults in config.py):
- `TEMPORAL_ADDRESS`: Temporal server address (localhost:7233)
- `ORDER_TASK_QUEUE`: Order worker queue name (order-tq)
- `SHIPPING_TASK_QUEUE`: Shipping worker queue name (shipping-tq)
- `DATABASE_URL`: PostgreSQL connection string
- `WORKFLOW_RUN_TIMEOUT_SECONDS`: Max workflow duration (15)

## Development

Install dependencies:
```bash
pip install -r requirements.txt
```

Run database migrations:
```bash
docker-compose up -d db
# Schema is auto-applied by order_worker on startup
```

## Monitoring

- **Temporal UI**: http://localhost:8233
  - View workflow execution history
  - See retry attempts and failures
  - Query workflow state
  
- **API Documentation**: http://localhost:8000/docs
  - Interactive API testing
  - Request/response schemas

- **Logs**: Check worker terminals for structured logs
  - Activity retries
  - State transitions
  - Error messages

## How It Works

### Complete Flow

1. **Start Workflow**: POST to /orders/{id}/start
2. **Receive Order**: Activity inserts into DB
3. **Validate Order**: Activity validates items
4. **Manual Review**: Workflow waits for approve signal
5. **Charge Payment**: Activity charges with idempotency
6. **Shipping Child**: Start ShippingWorkflow on separate queue
7. **Prepare Package**: Shipping activity
8. **Dispatch Carrier**: Shipping activity (signals parent if fails)
9. **Mark Shipped**: Final order activity
10. **Complete**: Workflow returns success

### Failure Handling

- **Activity timeout**: Retries with exponential backoff
- **Activity error**: Retries up to 10 times
- **Dispatch failure**: Child signals parent, parent can compensate
- **Manual review timeout**: Workflow fails after 5 minutes
- **Order cancellation**: Workflow exits gracefully

### Idempotency

All side effects are idempotent:
- Orders: Check by order_id before insert
- Payments: Use payment_id as primary key
- State updates: Update only if not already in target state
- Events: UUID-based IDs prevent duplicates

## Performance

Workflow timing with retry logic:
- **Activity timeout**: 2s per attempt
- **Retry policy**: Up to 1000 attempts, 5-200ms delays between retries
- **Manual approval**: 300s timeout (auto-approved in test)
- **Total time**: ~18-22 seconds with `flaky_call()` causing intentional failures
- Activities succeed eventually due to aggressive retry policy (33% success rate per attempt)

## Stop Services

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (clean slate)
docker-compose down -v
```
