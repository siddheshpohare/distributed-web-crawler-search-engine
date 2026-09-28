-- setup_db.sql — Manual Database Setup for Phase 2
--
-- Run this once against your PostgreSQL instance to create
-- the database and the pages table.
--
-- Usage:
--   psql -U postgres -f setup_db.sql
--
-- Or connect to psql and paste the statements manually.

-- Create the database (skip if it already exists).
-- Run this from the default 'postgres' database:
-- CREATE DATABASE crawlerdb;

-- Connect to crawlerdb, then run:

CREATE TABLE IF NOT EXISTS pages (
    id           SERIAL PRIMARY KEY,
    url          TEXT UNIQUE NOT NULL,
    title        TEXT,
    http_status  INTEGER,
    crawl_status TEXT,          -- 'success' | 'failed' | 'skipped'
    crawled_at   TIMESTAMPTZ DEFAULT now()
);

-- Index on url is created by the UNIQUE constraint above.
-- Add an index on crawl_status for filtered queries (optional but useful).
CREATE INDEX IF NOT EXISTS idx_pages_crawl_status ON pages (crawl_status);

-- Verify:
-- SELECT * FROM pages LIMIT 5;
