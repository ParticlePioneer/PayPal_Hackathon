-- Isolated test quotes: never use these as merchant-backed inventory.
CREATE TABLE IF NOT EXISTS payment_test_quotes (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS payment_quote_operation_unique
    ON payment_operations (quote_id, operation_type);
CREATE UNIQUE INDEX IF NOT EXISTS payment_order_unique
    ON payment_operations (paypal_order_id) WHERE operation_type = 'order' AND paypal_order_id IS NOT NULL;
