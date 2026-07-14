-- Migration 005: move former API-startup compatibility DDL into an explicit,
-- versioned migration. Every ADD/MODIFY/INDEX operation is guarded for safe
-- replay after MySQL's implicit DDL commits. No table or user data is dropped.

SET NAMES utf8mb4;

-- --------------------------------------------------------------------------
-- Delivery compatibility tables and columns
-- --------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `delivery_goods_config` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `goods_id` BIGINT NOT NULL,
  `config_json` LONGTEXT NOT NULL,
  `deleted` SMALLINT DEFAULT 0,
  `created_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_delivery_goods_config_goods` (`goods_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `delivery_text_source` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `title` VARCHAR(200) NOT NULL,
  `content` TEXT NULL,
  `remark` TEXT NULL,
  `deleted` SMALLINT DEFAULT 0,
  `created_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `delivery_template` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(200) NOT NULL,
  `type` INT DEFAULT 6,
  `status` SMALLINT DEFAULT 1,
  `content` TEXT NULL,
  `random_enabled` SMALLINT DEFAULT 0,
  `deleted` SMALLINT DEFAULT 0,
  `created_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `delivery_statement` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `enabled` SMALLINT DEFAULT 0,
  `content` TEXT NULL,
  `scope` VARCHAR(50) DEFAULT 'all',
  `deleted` SMALLINT DEFAULT 0,
  `created_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'card_group' AND column_name = 'card_prefix'),
  'SELECT 1',
  'ALTER TABLE `card_group` ADD COLUMN `card_prefix` VARCHAR(100) NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'card_group' AND column_name = 'password_prefix'),
  'SELECT 1',
  'ALTER TABLE `card_group` ADD COLUMN `password_prefix` VARCHAR(100) NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'card_group' AND column_name = 'alert_threshold'),
  'SELECT 1',
  'ALTER TABLE `card_group` ADD COLUMN `alert_threshold` INT DEFAULT 10'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'card_group' AND column_name = 'cost_price'),
  'SELECT 1',
  'ALTER TABLE `card_group` ADD COLUMN `cost_price` DECIMAL(12,2) DEFAULT 0'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'card_group' AND column_name = 'suggested_price'),
  'SELECT 1',
  'ALTER TABLE `card_group` ADD COLUMN `suggested_price` DECIMAL(12,2) DEFAULT 0'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'card_item' AND column_name = 'status'),
  'SELECT 1',
  'ALTER TABLE `card_item` ADD COLUMN `status` SMALLINT DEFAULT 0'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'card_item' AND column_name = 'used_order_id'),
  'SELECT 1',
  'ALTER TABLE `card_item` ADD COLUMN `used_order_id` BIGINT NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'delivery_record' AND column_name = 'delivery_mode'),
  'SELECT 1',
  'ALTER TABLE `delivery_record` ADD COLUMN `delivery_mode` VARCHAR(50) NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'delivery_record' AND column_name = 'delivery_content'),
  'SELECT 1',
  'ALTER TABLE `delivery_record` ADD COLUMN `delivery_content` TEXT NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'delivery_record' AND column_name = 'receiver_info'),
  'SELECT 1',
  'ALTER TABLE `delivery_record` ADD COLUMN `receiver_info` TEXT NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'delivery_record' AND column_name = 'delivery_timing'),
  'SELECT 1',
  'ALTER TABLE `delivery_record` ADD COLUMN `delivery_timing` VARCHAR(50) NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'delivery_record' AND column_name = 'status'),
  'SELECT 1',
  'ALTER TABLE `delivery_record` ADD COLUMN `status` SMALLINT DEFAULT 0'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'delivery_record' AND column_name = 'fail_reason'),
  'SELECT 1',
  'ALTER TABLE `delivery_record` ADD COLUMN `fail_reason` TEXT NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'delivery_record' AND column_name = 'delivery_time'),
  'SELECT 1',
  'ALTER TABLE `delivery_record` ADD COLUMN `delivery_time` DATETIME NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'delivery_record' AND column_name = 'completed_time'),
  'SELECT 1',
  'ALTER TABLE `delivery_record` ADD COLUMN `completed_time` DATETIME NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'delivery_record' AND column_name = 'quantity_requested'),
  'SELECT 1',
  'ALTER TABLE `delivery_record` ADD COLUMN `quantity_requested` INT DEFAULT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'delivery_record' AND column_name = 'quantity_sent'),
  'SELECT 1',
  'ALTER TABLE `delivery_record` ADD COLUMN `quantity_sent` INT DEFAULT 0'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'delivery_record' AND column_name = 'platform_sync_time'),
  'SELECT 1',
  'ALTER TABLE `delivery_record` ADD COLUMN `platform_sync_time` DATETIME NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'delivery_record' AND column_name = 'result'),
  'SELECT 1',
  'ALTER TABLE `delivery_record` ADD COLUMN `result` TEXT NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

UPDATE `card_item`
SET `status` = CASE
  WHEN COALESCE(`status`, 0) = 0 AND COALESCE(`is_used`, 0) = 1 THEN 2
  ELSE COALESCE(`status`, 0)
END
WHERE `deleted` = 0;

UPDATE `card_item`
SET `used_order_id` = COALESCE(`used_order_id`, `used_by_order_id`)
WHERE `used_order_id` IS NULL AND `used_by_order_id` IS NOT NULL;

UPDATE `delivery_record`
SET `status` = CASE
      WHEN `delivery_status` = 'success' THEN 2
      WHEN `delivery_status` = 'failed' THEN 3
      ELSE COALESCE(`status`, 0)
    END,
    `delivery_mode` = COALESCE(`delivery_mode`, `delivery_type`),
    `delivery_content` = COALESCE(`delivery_content`, `content`),
    `fail_reason` = COALESCE(`fail_reason`, `error_message`),
    `quantity_requested` = COALESCE(NULLIF(`quantity_requested`, 0), 1),
    `quantity_sent` = CASE
      WHEN COALESCE(`quantity_sent`, 0) > 0 THEN `quantity_sent`
      WHEN `delivery_status` = 'success' THEN 1
      ELSE 0
    END,
    `delivery_time` = COALESCE(`delivery_time`, CASE WHEN `delivery_status` = 'success' THEN `updated_time` END),
    `completed_time` = COALESCE(`completed_time`, CASE WHEN `delivery_status` = 'success' THEN `updated_time` END)
WHERE `deleted` = 0;

UPDATE `card_group` AS `g`
SET `total_count` = (
      SELECT COUNT(*) FROM `card_item` AS `i`
      WHERE `i`.`group_id` = `g`.`id` AND `i`.`deleted` = 0
    ),
    `used_count` = (
      SELECT COUNT(*) FROM `card_item` AS `i`
      WHERE `i`.`group_id` = `g`.`id` AND `i`.`deleted` = 0 AND `i`.`status` = 2
    ),
    `available_count` = (
      SELECT COUNT(*) FROM `card_item` AS `i`
      WHERE `i`.`group_id` = `g`.`id` AND `i`.`deleted` = 0 AND `i`.`status` = 0
    ),
    `updated_time` = NOW()
WHERE `g`.`deleted` = 0;

-- --------------------------------------------------------------------------
-- Model configuration compatibility
-- --------------------------------------------------------------------------

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'model_config' AND column_name = 'provider'),
  'SELECT 1',
  'ALTER TABLE `model_config` ADD COLUMN `provider` VARCHAR(100) NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'model_config' AND column_name = 'model_type'),
  'SELECT 1',
  'ALTER TABLE `model_config` ADD COLUMN `model_type` VARCHAR(50) NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'model_config' AND column_name = 'real_model'),
  'SELECT 1',
  'ALTER TABLE `model_config` ADD COLUMN `real_model` VARCHAR(200) NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'model_config' AND column_name = 'params_json'),
  'SELECT 1',
  'ALTER TABLE `model_config` ADD COLUMN `params_json` JSON NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'model_config' AND column_name = 'is_default'),
  'SELECT 1',
  'ALTER TABLE `model_config` ADD COLUMN `is_default` SMALLINT DEFAULT 0'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'model_config' AND column_name = 'remark'),
  'SELECT 1',
  'ALTER TABLE `model_config` ADD COLUMN `remark` TEXT NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'model_config' AND column_name = 'deleted'),
  'SELECT 1',
  'ALTER TABLE `model_config` ADD COLUMN `deleted` SMALLINT DEFAULT 0'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'model_config' AND column_name = 'created_time'),
  'SELECT 1',
  'ALTER TABLE `model_config` ADD COLUMN `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'model_config' AND column_name = 'provider_name'),
  'UPDATE `model_config` SET `provider` = COALESCE(NULLIF(`provider`, ''''), `provider_name`) WHERE `provider_name` IS NOT NULL AND `provider_name` <> ''''',
  'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'model_config' AND column_name = 'scene'),
  'UPDATE `model_config` SET `model_type` = COALESCE(NULLIF(`model_type`, ''''), `scene`, ''chat'')',
  'UPDATE `model_config` SET `model_type` = COALESCE(NULLIF(`model_type`, ''''), ''chat'')'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

UPDATE `model_config`
SET `real_model` = COALESCE(NULLIF(`real_model`, ''), `model_name`),
    `created_time` = COALESCE(`created_time`, `updated_time`, NOW()),
    `deleted` = COALESCE(`deleted`, 0),
    `is_default` = COALESCE(`is_default`, 0);

SET @ddl = IF(
  (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'model_config'
      AND column_name IN ('max_tokens', 'temperature', 'image_size', 'quality')
  ) = 4,
  'UPDATE `model_config` SET `params_json` = COALESCE(`params_json`, JSON_OBJECT(''maxTokens'', COALESCE(`max_tokens`, 0), ''temperature'', COALESCE(`temperature`, 0.70), ''imageSize'', `image_size`, ''quality'', `quality`))',
  'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.statistics
    WHERE table_schema = DATABASE() AND table_name = 'model_config'
      AND index_name = 'idx_model_config_type_status'
  ),
  'SELECT 1',
  'CREATE INDEX `idx_model_config_type_status` ON `model_config` (`model_type`, `status`)'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- --------------------------------------------------------------------------
-- RAG compatibility
-- --------------------------------------------------------------------------

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'rag_knowledge_base' AND column_name = 'name'),
  'SELECT 1',
  'ALTER TABLE `rag_knowledge_base` ADD COLUMN `name` VARCHAR(200) NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'rag_knowledge_base' AND column_name = 'embedding_model'),
  'SELECT 1',
  'ALTER TABLE `rag_knowledge_base` ADD COLUMN `embedding_model` VARCHAR(200) NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'rag_knowledge_base' AND column_name = 'embedding_api_key'),
  'SELECT 1',
  'ALTER TABLE `rag_knowledge_base` ADD COLUMN `embedding_api_key` TEXT NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'rag_knowledge_base' AND column_name = 'embedding_base_url'),
  'SELECT 1',
  'ALTER TABLE `rag_knowledge_base` ADD COLUMN `embedding_base_url` VARCHAR(500) NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'rag_knowledge_base' AND column_name = 'chunk_count'),
  'SELECT 1',
  'ALTER TABLE `rag_knowledge_base` ADD COLUMN `chunk_count` INT DEFAULT 0'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'rag_document' AND column_name = 'kb_id'),
  'SELECT 1',
  'ALTER TABLE `rag_document` ADD COLUMN `kb_id` BIGINT NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'rag_document' AND column_name = 'file_url'),
  'SELECT 1',
  'ALTER TABLE `rag_document` ADD COLUMN `file_url` TEXT NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'rag_document' AND column_name = 'file_type'),
  'SELECT 1',
  'ALTER TABLE `rag_document` ADD COLUMN `file_type` VARCHAR(50) NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'rag_document' AND column_name = 'error_message'),
  'SELECT 1',
  'ALTER TABLE `rag_document` ADD COLUMN `error_message` TEXT NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'rag_chunk' AND column_name = 'kb_id'),
  'SELECT 1',
  'ALTER TABLE `rag_chunk` ADD COLUMN `kb_id` BIGINT NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'rag_chunk' AND column_name = 'doc_id'),
  'SELECT 1',
  'ALTER TABLE `rag_chunk` ADD COLUMN `doc_id` BIGINT NULL'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'rag_chunk'
      AND column_name = 'embedding'
      AND data_type IN ('tinyblob', 'blob', 'mediumblob', 'longblob')
  ),
  'ALTER TABLE `rag_chunk` MODIFY COLUMN `embedding` LONGTEXT NULL',
  'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'rag_knowledge_base' AND column_name = 'knowledge_name'),
  'UPDATE `rag_knowledge_base` SET `name` = COALESCE(NULLIF(`name`, ''''), `knowledge_name`), `knowledge_name` = COALESCE(NULLIF(`knowledge_name`, ''''), `name`)',
  'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'rag_knowledge_base' AND column_name = 'vector_count'),
  'UPDATE `rag_knowledge_base` SET `chunk_count` = CASE WHEN COALESCE(`chunk_count`, 0) = 0 AND COALESCE(`vector_count`, 0) > 0 THEN `vector_count` ELSE COALESCE(`chunk_count`, 0) END',
  'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'rag_document' AND column_name = 'knowledge_base_id'),
  'UPDATE `rag_document` SET `kb_id` = COALESCE(`kb_id`, `knowledge_base_id`)',
  'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'rag_document' AND column_name = 'file_path'),
  'UPDATE `rag_document` SET `file_url` = COALESCE(NULLIF(`file_url`, ''''), `file_path`)',
  'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

UPDATE `rag_document`
SET `file_type` = CASE
  -- exec_driver_sql reaches the MySQL ``format`` paramstyle driver; double
  -- percent signs are decoded to literal SQL wildcards instead of being
  -- mistaken for Python interpolation tokens.
  WHEN COALESCE(NULLIF(`file_type`, ''), '') = '' AND `file_name` LIKE '%%.%%'
    THEN LOWER(SUBSTRING_INDEX(`file_name`, '.', -1))
  ELSE `file_type`
END;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'rag_chunk' AND column_name = 'knowledge_base_id'),
  'UPDATE `rag_chunk` SET `kb_id` = COALESCE(`kb_id`, `knowledge_base_id`)',
  'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'rag_chunk' AND column_name = 'document_id'),
  'UPDATE `rag_chunk` SET `doc_id` = COALESCE(`doc_id`, `document_id`)',
  'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

UPDATE `rag_knowledge_base` AS `kb`
SET `doc_count` = (
      SELECT COUNT(*) FROM `rag_document` AS `d`
      WHERE `d`.`kb_id` = `kb`.`id` AND COALESCE(`d`.`deleted`, 0) = 0
    ),
    `chunk_count` = (
      SELECT COUNT(*) FROM `rag_chunk` AS `c` WHERE `c`.`kb_id` = `kb`.`id`
    );

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'rag_knowledge_base' AND column_name = 'vector_count'),
  'UPDATE `rag_knowledge_base` SET `vector_count` = COALESCE(`chunk_count`, 0)',
  'SELECT 1'
);
PREPARE migration_stmt FROM @ddl;
EXECUTE migration_stmt;
DEALLOCATE PREPARE migration_stmt;

-- Version history is written by the migration runner after this file succeeds.
