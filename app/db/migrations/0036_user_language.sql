-- Migration 0036: Add language preference to users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS language VARCHAR(10) DEFAULT 'bn';
