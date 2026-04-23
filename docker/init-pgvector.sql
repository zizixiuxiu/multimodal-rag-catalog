-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Update search path
ALTER DATABASE multimodal_rag SET search_path TO public;
