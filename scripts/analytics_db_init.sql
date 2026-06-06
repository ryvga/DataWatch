-- ============================================================
-- DataWatch Analytics Database — analyticsdb
-- SaaS analytics schema for startup-io workspace demo
-- Connect: host=localhost port=5435 user=analytics_ro pass=readonly_pass db=analyticsdb
-- ============================================================

CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(50),
    event_name VARCHAR(100) NOT NULL,
    event_type VARCHAR(50),
    properties JSONB,
    session_id VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sessions (
    id VARCHAR(100) PRIMARY KEY,
    user_id VARCHAR(50),
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ended_at TIMESTAMP WITH TIME ZONE,
    duration_seconds INTEGER,
    pages_visited INTEGER DEFAULT 1,
    referrer VARCHAR(500),
    country VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(50) PRIMARY KEY,
    email VARCHAR(255) UNIQUE,
    plan VARCHAR(50) DEFAULT 'free',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen_at TIMESTAMP WITH TIME ZONE,
    mrr DECIMAL(10,2) DEFAULT 0,
    churn_risk DECIMAL(4,3)
);

CREATE TABLE IF NOT EXISTS feature_flags (
    id SERIAL PRIMARY KEY,
    flag_name VARCHAR(100) NOT NULL,
    enabled BOOLEAN DEFAULT false,
    rollout_pct INTEGER DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Seed users (8,400 active SaaS customers)
INSERT INTO users (id, email, plan, created_at, last_seen_at, mrr)
SELECT
    'usr_' || i,
    'user' || i || '@startup.io',
    CASE WHEN random() < 0.6 THEN 'free'
         WHEN random() < 0.82 THEN 'starter'
         WHEN random() < 0.95 THEN 'growth'
         ELSE 'enterprise' END,
    NOW() - make_interval(days => (random() * 180)::INTEGER),
    CASE WHEN random() < 0.7 THEN NOW() - make_interval(days => (random() * 14)::INTEGER) ELSE NULL END,
    CASE WHEN random() < 0.4 THEN round((random() * 299)::NUMERIC, 2) ELSE 0 END
FROM generate_series(1, 8400) i;

-- Seed sessions (180,000 — 45-day history, healthy)
INSERT INTO sessions (id, user_id, started_at, ended_at, duration_seconds, pages_visited, country)
SELECT
    'sess_' || i,
    'usr_' || (random() * 8399 + 1)::INTEGER,
    NOW() - make_interval(days => (random() * 45)::INTEGER),
    NOW() - make_interval(days => (random() * 44)::INTEGER),
    (random() * 1200 + 30)::INTEGER,
    (random() * 15 + 1)::INTEGER,
    CASE (random() * 5)::INTEGER
        WHEN 0 THEN 'United States'
        WHEN 1 THEN 'France'
        WHEN 2 THEN 'Germany'
        WHEN 3 THEN 'Morocco'
        ELSE 'United Kingdom' END
FROM generate_series(1, 180000) i;

-- Seed events (500,000 — 45-day history, healthy)
INSERT INTO events (user_id, event_name, event_type, session_id, created_at)
SELECT
    'usr_' || (random() * 8399 + 1)::INTEGER,
    CASE (random() * 8)::INTEGER
        WHEN 0 THEN 'page_view'
        WHEN 1 THEN 'signup'
        WHEN 2 THEN 'login'
        WHEN 3 THEN 'checkout_started'
        WHEN 4 THEN 'purchase_completed'
        WHEN 5 THEN 'subscription_upgraded'
        WHEN 6 THEN 'feature_used'
        ELSE 'dashboard_viewed' END,
    CASE (random() * 3)::INTEGER
        WHEN 0 THEN 'user_action'
        WHEN 1 THEN 'system'
        ELSE 'navigation' END,
    'sess_' || (random() * 179999 + 1)::INTEGER,
    NOW() - make_interval(days => (random() * 44)::INTEGER)
FROM generate_series(1, 500000) i;

-- ANOMALY 1: Last 3 hours — events.user_id is NULL (tracking pipeline broken)
INSERT INTO events (user_id, event_name, event_type, created_at)
SELECT
    NULL,   -- <-- user_id intentionally NULL (broken analytics SDK)
    CASE (random() * 3)::INTEGER
        WHEN 0 THEN 'page_view'
        WHEN 1 THEN 'feature_used'
        ELSE 'dashboard_viewed' END,
    'user_action',
    NOW() - make_interval(hours => (random() * 3)::INTEGER)
FROM generate_series(1, 12000) i;

-- ANOMALY 2: Last 2 hours — sessions.duration_seconds = 0 (session timeout bug)
INSERT INTO sessions (id, user_id, started_at, ended_at, duration_seconds, pages_visited)
SELECT
    'sess_broken_' || i,
    'usr_' || (random() * 8399 + 1)::INTEGER,
    NOW() - make_interval(hours => (random() * 2)::INTEGER),
    NOW() - make_interval(hours => (random() * 2)::INTEGER),
    0,   -- <-- zero-duration sessions (bug)
    1
FROM generate_series(1, 3500) i;

-- Feature flags table (small reference table)
INSERT INTO feature_flags (flag_name, enabled, rollout_pct, updated_at)
VALUES
    ('new_dashboard', true, 100, NOW()),
    ('ai_recommendations', true, 50, NOW() - '2 days'::INTERVAL),
    ('beta_export', false, 0, NOW() - '7 days'::INTERVAL),
    ('advanced_filters', true, 25, NOW() - '1 day'::INTERVAL);

-- Grant read access
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analytics_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO analytics_ro;
