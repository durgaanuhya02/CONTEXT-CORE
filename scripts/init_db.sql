-- ContextCore Database Schema

CREATE TABLE IF NOT EXISTS knowledge_nodes (
    id              TEXT PRIMARY KEY,          -- graphrag entity id
    title           TEXT NOT NULL,             -- entity name
    description     TEXT,                      -- graphrag summary
    source_system   TEXT,                      -- slack | confluence | github | zoom
    source_file     TEXT,                      -- original file name
    author_id       TEXT,                      -- who created this knowledge
    created_at      TIMESTAMP,                 -- original creation date
    last_validated  TIMESTAMP DEFAULT NOW(),   -- last time this was confirmed accurate
    decay_score     FLOAT DEFAULT 1.0,         -- 1.0 = fresh, 0.0 = stale
    community_id    TEXT,                      -- graphrag community id
    tags            TEXT[],                    -- topic tags
    inserted_at     TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge_owners (
    id              SERIAL PRIMARY KEY,
    author_id       TEXT NOT NULL,             -- e.g. alice.chen
    email           TEXT,
    role            TEXT,
    node_count      INT DEFAULT 0,             -- how many nodes they own
    risk_score      FLOAT DEFAULT 0.0,         -- 0.0 = low, 1.0 = critical
    is_active       BOOLEAN DEFAULT TRUE,      -- false = left company
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_log (
    id              SERIAL PRIMARY KEY,
    query_text      TEXT NOT NULL,
    answer          TEXT,
    source_nodes    TEXT[],                    -- entity ids used in answer
    source_files    TEXT[],                    -- source files referenced
    confidence      FLOAT,                     -- answer confidence score
    query_method    TEXT DEFAULT 'local',      -- local | global | drift
    user_id         TEXT DEFAULT 'demo_user',
    queried_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS risk_scores (
    id              SERIAL PRIMARY KEY,
    domain          TEXT NOT NULL,             -- e.g. billing-service, istio
    owner_id        TEXT NOT NULL,             -- primary owner
    risk_level      TEXT NOT NULL,             -- LOW | MEDIUM | HIGH | CRITICAL
    risk_score      FLOAT NOT NULL,            -- 0.0 to 1.0
    reason          TEXT,                      -- human-readable explanation
    node_count      INT DEFAULT 0,             -- nodes in this domain
    sole_owner      BOOLEAN DEFAULT FALSE,     -- true = single point of failure
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- Coverage gaps: topics queried but not documented
CREATE TABLE IF NOT EXISTS coverage_gaps (
    id              SERIAL PRIMARY KEY,
    topic           TEXT NOT NULL,
    query_count     INT DEFAULT 1,        -- how many times queried
    node_count      INT DEFAULT 0,        -- how many nodes document it
    gap_score       FLOAT DEFAULT 1.0,    -- 1.0 = completely undocumented
    first_queried   TIMESTAMP DEFAULT NOW(),
    last_queried    TIMESTAMP DEFAULT NOW()
);

-- Regulatory tags per knowledge node
CREATE TABLE IF NOT EXISTS regulatory_tags (
    id              SERIAL PRIMARY KEY,
    node_id         TEXT NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    framework       TEXT NOT NULL,        -- SOX | GDPR | HIPAA | EU_AI_ACT | ISO_42001
    rationale       TEXT,
    tagged_at       TIMESTAMP DEFAULT NOW()
);

-- Tamper-evident audit chain (each entry hashes previous)
ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS entry_hash TEXT;
ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS prev_hash  TEXT;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_nodes_author ON knowledge_nodes(author_id);
CREATE INDEX IF NOT EXISTS idx_nodes_source ON knowledge_nodes(source_system);
CREATE INDEX IF NOT EXISTS idx_nodes_decay ON knowledge_nodes(decay_score);
CREATE INDEX IF NOT EXISTS idx_audit_queried ON audit_log(queried_at DESC);
CREATE INDEX IF NOT EXISTS idx_risk_level ON risk_scores(risk_level);
CREATE INDEX IF NOT EXISTS idx_gaps_score ON coverage_gaps(gap_score DESC);
CREATE INDEX IF NOT EXISTS idx_reg_tags_node ON regulatory_tags(node_id);
CREATE INDEX IF NOT EXISTS idx_reg_tags_framework ON regulatory_tags(framework);
