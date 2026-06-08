-- ============================================================
-- DataWatch Startup Analytics Database — analyticsdb
-- SaaS analytics schema for startup-io demo workspace
-- Initial state: CLEAN / HEALTHY — simulator injects anomalies
--
-- Read:  postgresql://analytics_ro:readonly_pass@localhost:5435/analyticsdb
-- Write: postgresql://write_user:write_pass@localhost:5435/analyticsdb
-- ============================================================

CREATE TABLE IF NOT EXISTS events (
    id         BIGSERIAL PRIMARY KEY,
    user_id    VARCHAR(50),
    event_name VARCHAR(100) NOT NULL,
    event_type VARCHAR(50),
    properties JSONB,
    session_id VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sessions (
    id               VARCHAR(100) PRIMARY KEY,
    user_id          VARCHAR(50),
    started_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ended_at         TIMESTAMP WITH TIME ZONE,
    duration_seconds INTEGER,
    pages_visited    INTEGER DEFAULT 1,
    referrer         VARCHAR(500),
    country          VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS users (
    id          VARCHAR(50) PRIMARY KEY,
    email       VARCHAR(255) UNIQUE,
    plan        VARCHAR(50) DEFAULT 'free',
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen_at TIMESTAMP WITH TIME ZONE,
    mrr         DECIMAL(10,2) DEFAULT 0,
    churn_risk  DECIMAL(4,3)
);

CREATE TABLE IF NOT EXISTS feature_flags (
    id          SERIAL PRIMARY KEY,
    flag_name   VARCHAR(100) NOT NULL,
    enabled     BOOLEAN DEFAULT false,
    rollout_pct INTEGER DEFAULT 0,
    updated_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ── Access grants ──────────────────────────────────────────────────────────

-- Write user for the simulator
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'write_user') THEN
    CREATE ROLE write_user WITH LOGIN PASSWORD 'write_pass';
  END IF;
END$$;
GRANT CONNECT ON DATABASE analyticsdb TO write_user;
GRANT USAGE ON SCHEMA public TO write_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO write_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO write_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO write_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO write_user;

-- analytics_ro is the container's default postgres superuser
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analytics_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO analytics_ro;

-- ── Seed data (clean healthy baseline) ────────────────────────────────────

-- 8,400 SaaS users
INSERT INTO users (id, email, plan, created_at, last_seen_at, mrr)
SELECT
    'usr_' || i,
    'user' || i || '@startup.io',
    CASE WHEN (i % 10) < 6 THEN 'free'
         WHEN (i % 10) < 8 THEN 'starter'
         WHEN (i % 10) < 10 THEN 'growth'
         ELSE 'enterprise' END,
    NOW() - make_interval(days => (random() * 180)::INTEGER),
    CASE WHEN random() < 0.7
         THEN NOW() - make_interval(days => (random() * 14)::INTEGER)
         ELSE NULL END,
    CASE WHEN (i % 10) >= 6
         THEN round((random() * 299)::NUMERIC, 2)
         ELSE 0 END
FROM generate_series(1, 8400) i;

-- 180,000 sessions, 45-day history, healthy durations
INSERT INTO sessions (id, user_id, started_at, ended_at, duration_seconds, pages_visited, country)
SELECT
    'sess_' || i,
    'usr_' || (floor(random() * 8399 + 1))::INTEGER,
    NOW() - make_interval(days => (random() * 45)::INTEGER),
    NOW() - make_interval(days => (random() * 44)::INTEGER),
    (floor(random() * 1170 + 30))::INTEGER,
    (floor(random() * 15 + 1))::INTEGER,
    CASE (floor(random() * 5))::INTEGER
        WHEN 0 THEN 'United States'
        WHEN 1 THEN 'France'
        WHEN 2 THEN 'Germany'
        WHEN 3 THEN 'Morocco'
        ELSE 'United Kingdom' END
FROM generate_series(1, 180000) i;

-- 500,000 events, 45-day history, healthy user_id fill rate (~2% null — normal tracking gaps)
INSERT INTO events (user_id, event_name, event_type, session_id, created_at)
SELECT
    CASE WHEN random() < 0.02 THEN NULL
         ELSE 'usr_' || (floor(random() * 8399 + 1))::INTEGER END,
    CASE (floor(random() * 8))::INTEGER
        WHEN 0 THEN 'page_view'
        WHEN 1 THEN 'signup'
        WHEN 2 THEN 'login'
        WHEN 3 THEN 'checkout_started'
        WHEN 4 THEN 'purchase_completed'
        WHEN 5 THEN 'subscription_upgraded'
        WHEN 6 THEN 'feature_used'
        ELSE 'dashboard_viewed' END,
    CASE (floor(random() * 3))::INTEGER
        WHEN 0 THEN 'user_action'
        WHEN 1 THEN 'system'
        ELSE 'navigation' END,
    'sess_' || (floor(random() * 179999 + 1))::INTEGER,
    NOW() - make_interval(days => (random() * 44)::INTEGER)
FROM generate_series(1, 500000) i;

-- Feature flags
INSERT INTO feature_flags (flag_name, enabled, rollout_pct, updated_at)
VALUES
    ('new_dashboard',       true,  100, NOW()),
    ('ai_recommendations',  true,   50, NOW() - '2 days'::INTERVAL),
    ('beta_export',         false,   0, NOW() - '7 days'::INTERVAL),
    ('advanced_filters',    true,   25, NOW() - '1 day'::INTERVAL);
