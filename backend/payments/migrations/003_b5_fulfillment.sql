-- Only verified integrated authorizations with committed allocation can be fulfilled.
CREATE TABLE payment_fulfillments (
    authorization_operation_id TEXT PRIMARY KEY REFERENCES payment_operations(operation_id),
    confirmed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
