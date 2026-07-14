-- Migration 003: make credential columns large enough for AES-GCM envelopes.
-- Every DDL operation is guarded so a process interrupted after MySQL's
-- implicit DDL commit can safely replay the complete file.

SET NAMES utf8mb4;

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'model_config'
      AND column_name = 'api_key'
  ),
  'ALTER TABLE `model_config` MODIFY COLUMN `api_key` TEXT NULL COMMENT ''AES-GCM encrypted API credential''',
  'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'xianyu_ai_provider'
      AND column_name = 'api_key'
  ),
  'ALTER TABLE `xianyu_ai_provider` MODIFY COLUMN `api_key` TEXT NULL COMMENT ''AES-GCM encrypted API credential''',
  'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'rag_knowledge_base'
      AND column_name = 'embedding_api_key'
  ),
  'ALTER TABLE `rag_knowledge_base` MODIFY COLUMN `embedding_api_key` TEXT NULL COMMENT ''AES-GCM encrypted embedding credential''',
  'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- Version history is written by the migration runner after this file succeeds.
