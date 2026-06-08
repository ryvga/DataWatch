-- ============================================================
-- DataWatch Acme Database — acmedb
-- E-commerce schema for acme-corp demo workspace
-- Initial state: CLEAN / HEALTHY — simulator injects anomalies
--
-- Read:  postgresql://readonly_user:readonly_pass@localhost:5434/acmedb
-- Write: postgresql://write_user:write_pass@localhost:5434/acmedb
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id          SERIAL PRIMARY KEY,
    email       VARCHAR(255) UNIQUE NOT NULL,
    full_name   VARCHAR(255),
    plan        VARCHAR(50) DEFAULT 'free',
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login_at TIMESTAMP WITH TIME ZONE,
    is_active   BOOLEAN DEFAULT true
);

CREATE TABLE IF NOT EXISTS products (
    id             SERIAL PRIMARY KEY,
    name           VARCHAR(255) NOT NULL,
    category       VARCHAR(100),
    price          DECIMAL(10,2) NOT NULL,
    stock_quantity INTEGER DEFAULT 0,
    sku            VARCHAR(100) UNIQUE,
    created_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
    id                SERIAL PRIMARY KEY,
    user_id           INTEGER REFERENCES users(id),
    status            VARCHAR(50) NOT NULL,
    total_amount      DECIMAL(10,2),
    payment_status    VARCHAR(50),
    payment_reference VARCHAR(255),
    currency          VARCHAR(10) DEFAULT 'USD',
    country           VARCHAR(50),
    created_at        TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    paid_at           TIMESTAMP WITH TIME ZONE,
    shipped_at        TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS order_items (
    id          SERIAL PRIMARY KEY,
    order_id    INTEGER REFERENCES orders(id),
    product_id  INTEGER REFERENCES products(id),
    quantity    INTEGER NOT NULL,
    unit_price  DECIMAL(10,2) NOT NULL,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payments (
    id           SERIAL PRIMARY KEY,
    order_id     INTEGER REFERENCES orders(id),
    amount       DECIMAL(10,2) NOT NULL,
    method       VARCHAR(50),
    status       VARCHAR(50),
    processor_id VARCHAR(255),
    created_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS events (
    id         BIGSERIAL PRIMARY KEY,
    user_id    INTEGER,
    event_name VARCHAR(100) NOT NULL,
    properties JSONB,
    session_id VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ── Access grants ──────────────────────────────────────────────────────────

-- Write user for the simulator
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'write_user') THEN
    CREATE ROLE write_user WITH LOGIN PASSWORD 'write_pass';
  END IF;
END$$;
GRANT CONNECT ON DATABASE "acmedb" TO write_user;
GRANT USAGE ON SCHEMA public TO write_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO write_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO write_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO write_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO write_user;

-- readonly_user is the container's default postgres superuser, grant read access explicitly
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_user;

-- ── Seed data (clean healthy baseline) ────────────────────────────────────

-- 12,000 users, 90-day history
INSERT INTO users (email, full_name, plan, created_at, last_login_at, is_active)
SELECT
    'user' || i || '@acme.io',
    'User ' || i,
    CASE WHEN (i % 10) < 7 THEN 'free'
         WHEN (i % 10) < 9 THEN 'starter'
         WHEN (i % 10) < 10 THEN 'growth'
         ELSE 'enterprise' END,
    NOW() - (floor(random() * 90)::INTEGER || ' days')::INTERVAL
          - (floor(random() * 23)::INTEGER || ' hours')::INTERVAL,
    CASE WHEN random() < 0.6
         THEN NOW() - (floor(random() * 30)::INTEGER || ' days')::INTERVAL
         ELSE NULL END,
    random() > 0.05
FROM generate_series(1, 12000) i;

-- 3,500 products
INSERT INTO products (name, category, price, stock_quantity, sku, created_at)
SELECT
    CASE (i % 6)
        WHEN 0 THEN 'Pro Plan - ' || i
        WHEN 1 THEN 'Growth Plan - ' || i
        WHEN 2 THEN 'Analytics Bundle - ' || i
        WHEN 3 THEN 'Enterprise Suite - ' || i
        WHEN 4 THEN 'Setup Service - ' || i
        ELSE 'Consulting Package - ' || i
    END,
    CASE (i % 3)
        WHEN 0 THEN 'Software'
        WHEN 1 THEN 'Service'
        ELSE 'Bundle'
    END,
    round((
        CASE (i % 6)
            WHEN 0 THEN 49.00
            WHEN 1 THEN 149.00
            WHEN 2 THEN 199.00
            WHEN 3 THEN 999.00
            WHEN 4 THEN 299.00
            ELSE 150.00
        END + (random() * 20)
    )::NUMERIC, 2),
    (floor(random() * 9999 + 1))::INTEGER,
    'SKU-' || lpad(i::TEXT, 5, '0'),
    NOW() - (floor(random() * 365)::INTEGER || ' days')::INTERVAL
FROM generate_series(1, 3500) i;

-- 8,500 orders, 90-day history, healthy payment_status distribution
INSERT INTO orders (user_id, status, total_amount, payment_status, payment_reference, currency, country, created_at, paid_at)
SELECT
    (floor(random() * 11999 + 1))::INTEGER,
    CASE WHEN random() < 0.75 THEN 'completed'
         WHEN random() < 0.87 THEN 'processing'
         WHEN random() < 0.94 THEN 'pending'
         ELSE 'cancelled' END,
    round((random() * 900 + 49)::NUMERIC, 2),
    CASE WHEN random() < 0.86 THEN 'paid'
         WHEN random() < 0.95 THEN 'pending'
         ELSE 'failed' END,
    'PAY-' || substr(md5(i::TEXT || random()::TEXT), 1, 20),
    CASE WHEN random() < 0.82 THEN 'USD'
         WHEN random() < 0.92 THEN 'EUR'
         ELSE 'MAD' END,
    CASE (floor(random() * 5))::INTEGER
        WHEN 0 THEN 'United States'
        WHEN 1 THEN 'France'
        WHEN 2 THEN 'Morocco'
        WHEN 3 THEN 'Germany'
        ELSE 'United Kingdom' END,
    NOW() - (floor(random() * 89)::INTEGER || ' days')::INTERVAL
          - (floor(random() * 23)::INTEGER || ' hours')::INTERVAL,
    CASE WHEN random() < 0.82
         THEN NOW() - (floor(random() * 89)::INTEGER || ' days')::INTERVAL
         ELSE NULL END
FROM generate_series(1, 8500) i;

-- ~7,000 payment records
INSERT INTO payments (order_id, amount, method, status, processor_id, created_at, processed_at)
SELECT
    o.id,
    o.total_amount,
    CASE WHEN random() < 0.55 THEN 'card'
         WHEN random() < 0.80 THEN 'paypal'
         ELSE 'bank_transfer' END,
    CASE WHEN o.payment_status = 'paid'    THEN 'completed'
         WHEN o.payment_status = 'pending' THEN 'pending'
         ELSE 'failed' END,
    'PP-' || substr(md5(o.id::TEXT), 1, 24),
    o.created_at + '5 minutes'::INTERVAL,
    CASE WHEN o.payment_status = 'paid'
         THEN o.created_at + '10 minutes'::INTERVAL
         ELSE NULL END
FROM orders o
WHERE o.total_amount > 0 AND o.payment_status IS NOT NULL
ORDER BY o.created_at DESC
LIMIT 7000;

-- 200,000 events, 30-day history
INSERT INTO events (user_id, event_name, session_id, created_at)
SELECT
    (floor(random() * 11999 + 1))::INTEGER,
    CASE (floor(random() * 7))::INTEGER
        WHEN 0 THEN 'page_view'
        WHEN 1 THEN 'signup'
        WHEN 2 THEN 'login'
        WHEN 3 THEN 'checkout_started'
        WHEN 4 THEN 'purchase_completed'
        WHEN 5 THEN 'subscription_upgraded'
        ELSE 'feature_used' END,
    'sess-' || substr(md5(random()::TEXT), 1, 16),
    NOW() - (floor(random() * 30)::INTEGER || ' days')::INTERVAL
          - (floor(random() * 23)::INTEGER || ' hours')::INTERVAL
FROM generate_series(1, 200000) i;

-- ── Monitoring views ───────────────────────────────────────────────────────

CREATE OR REPLACE VIEW order_health AS
SELECT
    COUNT(*)                                                                         AS total_orders,
    COUNT(CASE WHEN payment_status IS NULL THEN 1 END)                               AS null_payment_status,
    ROUND(COUNT(CASE WHEN payment_status IS NULL THEN 1 END)::NUMERIC
          / GREATEST(COUNT(*), 1) * 100, 2)                                          AS null_pct,
    COUNT(CASE WHEN total_amount < 0 THEN 1 END)                                     AS negative_amounts,
    MAX(created_at)                                                                  AS last_order_at,
    NOW() - MAX(created_at)                                                          AS age
FROM orders;

GRANT SELECT ON order_health TO readonly_user;
GRANT SELECT ON order_health TO write_user;
