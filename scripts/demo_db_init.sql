-- ============================================================
-- DataWatch Demo Database — shopDemo
-- Realistic e-commerce schema with built-in anomalies for demo
-- Connect: host=localhost port=5434 user=readonly_user pass=readonly_pass db=shopDemo
-- ============================================================

-- Create tables
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255),
    plan VARCHAR(50) DEFAULT 'free',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true
);

CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    price DECIMAL(10,2) NOT NULL,
    stock_quantity INTEGER DEFAULT 0,
    sku VARCHAR(100) UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    status VARCHAR(50) NOT NULL,
    total_amount DECIMAL(10,2),
    payment_status VARCHAR(50),
    payment_reference VARCHAR(255),
    currency VARCHAR(10) DEFAULT 'USD',
    country VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    paid_at TIMESTAMP WITH TIME ZONE,
    shipped_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    amount DECIMAL(10,2) NOT NULL,
    method VARCHAR(50),
    status VARCHAR(50),
    processor_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER,
    event_name VARCHAR(100) NOT NULL,
    properties JSONB,
    session_id VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Read-only role for monitoring
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'datawatch_ro') THEN
    CREATE ROLE datawatch_ro;
  END IF;
END$$;
GRANT CONNECT ON DATABASE "shopDemo" TO readonly_user;
GRANT USAGE ON SCHEMA public TO readonly_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_user;

-- ── Seed users (12,000+ across 90 days) ───────────────────────────────────
INSERT INTO users (email, full_name, plan, created_at, last_login_at, is_active)
SELECT
    'user' || i || '@example.com',
    'User ' || i,
    CASE WHEN random() < 0.7 THEN 'free'
         WHEN random() < 0.85 THEN 'starter'
         WHEN random() < 0.95 THEN 'growth'
         ELSE 'enterprise' END,
    NOW() - (random() * 90 || ' days')::INTERVAL,
    CASE WHEN random() < 0.6 THEN NOW() - (random() * 30 || ' days')::INTERVAL ELSE NULL END,
    random() > 0.05
FROM generate_series(1, 12000) i;

-- ── Seed products ──────────────────────────────────────────────────────────
INSERT INTO products (name, category, price, stock_quantity, sku, created_at)
VALUES
    ('DataWatch Pro Subscription', 'Software', 49.00, 9999, 'DW-PRO-001', NOW() - '180 days'::INTERVAL),
    ('DataWatch Growth Plan', 'Software', 149.00, 9999, 'DW-GROWTH-002', NOW() - '180 days'::INTERVAL),
    ('DataWatch Agency Plan', 'Software', 299.00, 9999, 'DW-AGENCY-003', NOW() - '180 days'::INTERVAL),
    ('DataWatch Enterprise', 'Software', 999.00, 9999, 'DW-ENT-004', NOW() - '180 days'::INTERVAL),
    ('Setup Consulting', 'Service', 299.00, 100, 'SVC-SETUP-001', NOW() - '90 days'::INTERVAL),
    ('Data Audit Report', 'Service', 599.00, 50, 'SVC-AUDIT-001', NOW() - '60 days'::INTERVAL);

-- ── Seed orders (90 days history, healthy pattern) ────────────────────────
INSERT INTO orders (user_id, status, total_amount, payment_status, payment_reference, currency, country, created_at, paid_at)
SELECT
    (random() * 11999 + 1)::INTEGER,
    CASE WHEN random() < 0.75 THEN 'completed'
         WHEN random() < 0.87 THEN 'processing'
         WHEN random() < 0.94 THEN 'pending'
         ELSE 'cancelled' END,
    round((random() * 900 + 49)::NUMERIC, 2),
    CASE WHEN random() < 0.82 THEN 'paid'
         WHEN random() < 0.92 THEN 'pending'
         ELSE 'failed' END,
    CASE WHEN random() < 0.85 THEN 'PAY-' || md5(random()::TEXT)::VARCHAR(20) ELSE NULL END,
    CASE WHEN random() < 0.85 THEN 'USD' ELSE CASE WHEN random() < 0.5 THEN 'EUR' ELSE 'MAD' END END,
    CASE (random() * 4)::INTEGER
        WHEN 0 THEN 'United States'
        WHEN 1 THEN 'France'
        WHEN 2 THEN 'Morocco'
        WHEN 3 THEN 'Germany'
        ELSE 'United Kingdom' END,
    NOW() - (random() * 89 || ' days')::INTERVAL,
    CASE WHEN random() < 0.8 THEN NOW() - (random() * 89 || ' days')::INTERVAL ELSE NULL END
FROM generate_series(1, 8500) i;

-- ── ANOMALY 1: Last 6 hours — payment_status NULL spike (was 1%, now 35%) ─
-- This is the key demo incident that DataWatch will catch
INSERT INTO orders (user_id, status, total_amount, payment_status, payment_reference, currency, country, created_at, paid_at)
SELECT
    (random() * 11999 + 1)::INTEGER,
    'completed',
    round((random() * 500 + 49)::NUMERIC, 2),
    NULL,  -- <-- payment_status intentionally NULL (broken checkout)
    NULL,  -- <-- no payment reference either
    'USD',
    'United States',
    NOW() - (random() * 6 || ' hours')::INTERVAL,
    NULL
FROM generate_series(1, 340) i;

-- ── ANOMALY 2: Recent orders with negative amounts (data corruption) ───────
INSERT INTO orders (user_id, status, total_amount, payment_status, currency, country, created_at)
SELECT
    (random() * 11999 + 1)::INTEGER,
    'processing',
    round((-1 * random() * 50)::NUMERIC, 2),  -- NEGATIVE amounts
    'pending',
    'USD',
    'United States',
    NOW() - (random() * 2 || ' hours')::INTERVAL
FROM generate_series(1, 45) i;

-- ── ANOMALY 3: Users with duplicate emails (data quality) ─────────────────
INSERT INTO users (email, full_name, plan, created_at)
SELECT 'duplicate@example.com', 'Duplicate User ' || i, 'free', NOW() - (i || ' minutes')::INTERVAL
FROM generate_series(1, 15) i;

-- ── Seed payments ──────────────────────────────────────────────────────────
INSERT INTO payments (order_id, amount, method, status, processor_id, created_at, processed_at)
SELECT
    o.id,
    o.total_amount,
    CASE WHEN random() < 0.6 THEN 'paypal'
         WHEN random() < 0.85 THEN 'card'
         ELSE 'bank_transfer' END,
    CASE WHEN o.payment_status = 'paid' THEN 'completed'
         WHEN o.payment_status = 'pending' THEN 'pending'
         ELSE 'failed' END,
    'PP-' || md5(o.id::TEXT)::VARCHAR(24),
    o.created_at + '5 minutes'::INTERVAL,
    CASE WHEN o.payment_status = 'paid' THEN o.created_at + '10 minutes'::INTERVAL ELSE NULL END
FROM orders o
WHERE o.total_amount > 0
LIMIT 7000;

-- ── Seed events (high volume) ──────────────────────────────────────────────
INSERT INTO events (user_id, event_name, session_id, created_at)
SELECT
    (random() * 11999 + 1)::INTEGER,
    CASE (random() * 7)::INTEGER
        WHEN 0 THEN 'page_view'
        WHEN 1 THEN 'signup'
        WHEN 2 THEN 'login'
        WHEN 3 THEN 'checkout_started'
        WHEN 4 THEN 'purchase_completed'
        WHEN 5 THEN 'subscription_upgraded'
        ELSE 'feature_used' END,
    'sess-' || md5(random()::TEXT)::VARCHAR(16),
    NOW() - (random() * 30 || ' days')::INTERVAL
FROM generate_series(1, 250000) i;

-- ── Useful views for monitoring ────────────────────────────────────────────
CREATE OR REPLACE VIEW daily_revenue AS
SELECT
    date_trunc('day', created_at)::DATE AS day,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_revenue,
    AVG(total_amount) AS avg_order_value,
    COUNT(CASE WHEN payment_status IS NULL THEN 1 END) AS missing_payment_status
FROM orders
GROUP BY 1
ORDER BY 1 DESC;

CREATE OR REPLACE VIEW order_health_summary AS
SELECT
    COUNT(*) AS total_orders,
    COUNT(CASE WHEN payment_status IS NULL THEN 1 END) AS null_payment_status,
    ROUND(COUNT(CASE WHEN payment_status IS NULL THEN 1 END)::NUMERIC / COUNT(*) * 100, 2) AS null_pct,
    COUNT(CASE WHEN total_amount < 0 THEN 1 END) AS negative_amounts,
    COUNT(CASE WHEN payment_status = 'paid' AND payment_reference IS NULL THEN 1 END) AS paid_without_reference
FROM orders;

-- Confirm read access for monitoring user
GRANT SELECT ON daily_revenue TO readonly_user;
GRANT SELECT ON order_health_summary TO readonly_user;
