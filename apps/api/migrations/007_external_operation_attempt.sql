-- Migration 007: durable publish/update-price operation attempts.
-- 006 is reserved for remote-delete safety.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `external_operation_attempt` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `operation_type` VARCHAR(32) NOT NULL,
  `account_id` BIGINT NOT NULL,
  `idempotency_key` VARCHAR(128) NOT NULL,
  `request_digest` CHAR(64) NOT NULL,
  `target_local_id` BIGINT NULL,
  `remote_reference_id` VARCHAR(200) NULL,
  `remote_reference_url` TEXT NULL,
  `state` VARCHAR(32) NOT NULL DEFAULT 'pending'
    COMMENT 'pending/in_progress/remote_confirmed/confirmed/failed/unknown',
  `retry_scope` VARCHAR(32) NULL COMMENT 'remote/local_persist',
  `retry_safe` SMALLINT NOT NULL DEFAULT 1,
  `attempt_count` INT NOT NULL DEFAULT 0,
  `lease_token` VARCHAR(64) NULL,
  `lease_until` DATETIME NULL,
  `remote_started_at` DATETIME NULL,
  `remote_confirmed_at` DATETIME NULL,
  `local_confirmed_at` DATETIME NULL,
  `local_result_id` BIGINT NULL,
  `last_error_code` VARCHAR(64) NULL,
  `error_message` VARCHAR(500) NULL,
  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_external_operation_attempt_key` (`idempotency_key`),
  KEY `idx_external_operation_state_lease` (`operation_type`, `state`, `lease_until`),
  KEY `idx_external_operation_target` (`operation_type`, `target_local_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='外部商品操作的幂等与补偿状态';
