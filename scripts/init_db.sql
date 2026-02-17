-- =============================================================================
-- KORGAN AI — Database Initialization
-- PostgreSQL 16
-- =============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Conversations
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    interface TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    summary TEXT,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Messages
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    reasoning TEXT,
    tokens_used INTEGER DEFAULT 0,
    model_used TEXT,
    interface TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Facts (extracted knowledge)
CREATE TABLE IF NOT EXISTS facts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    category TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    confidence FLOAT DEFAULT 1.0,
    source_message_id UUID REFERENCES messages(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Audit Log
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    action TEXT NOT NULL,
    agent TEXT,
    details JSONB DEFAULT '{}'::jsonb,
    risk_level TEXT DEFAULT 'low' CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    autonomy_level TEXT,
    approved_by TEXT,
    rollback_data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Agent Actions
CREATE TABLE IF NOT EXISTS agent_actions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_name TEXT NOT NULL,
    action_type TEXT NOT NULL,
    input_data JSONB DEFAULT '{}'::jsonb,
    output_data JSONB DEFAULT '{}'::jsonb,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'success', 'failed', 'rolled_back')),
    duration_ms INTEGER,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Self-Analysis Reports
CREATE TABLE IF NOT EXISTS self_analysis_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    total_actions INTEGER DEFAULT 0,
    success_rate FLOAT DEFAULT 0,
    overall_score FLOAT DEFAULT 0,
    report_text TEXT,
    suggestions JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_role ON messages(role);
CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
CREATE INDEX IF NOT EXISTS idx_facts_key ON facts(key);
CREATE INDEX IF NOT EXISTS idx_facts_key_trgm ON facts USING gin (key gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_agent ON audit_log(agent);
CREATE INDEX IF NOT EXISTS idx_audit_risk ON audit_log(risk_level);
CREATE INDEX IF NOT EXISTS idx_agent_actions_agent ON agent_actions(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_actions_status ON agent_actions(status);
CREATE INDEX IF NOT EXISTS idx_agent_actions_created ON agent_actions(created_at DESC);

-- Initial data: System identity fact
INSERT INTO facts (category, key, value, confidence) VALUES
    ('system', 'creator', 'Amanat Korgan (Мистер Корган)', 1.0),
    ('system', 'codename', 'KORGAN AI', 1.0),
    ('system', 'version', '1.0.0', 1.0),
    ('system', 'personality', 'strategic, calm, concise, respectful', 1.0)
ON CONFLICT DO NOTHING;

-- Log system initialization
INSERT INTO audit_log (action, details, risk_level) VALUES
    ('database_initialized', '{"version": "1.0.0"}'::jsonb, 'low');
