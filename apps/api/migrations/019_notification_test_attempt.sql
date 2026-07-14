-- Migration 019: durable at-most-once state for operator notification tests.
-- The attempt table stores only routing identity, request digests, bounded
-- provider metadata and state.  It intentionally excludes channel secrets,
-- request/response bodies, notification text and rendered content.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `notification_test_attempt` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `user_id` BIGINT NOT NULL,
  `channel_key` VARCHAR(80) NOT NULL,
  `idempotency_key` VARCHAR(128) NOT NULL,
  `payload_digest` CHAR(64) NOT NULL COMMENT 'SHA-256 only; no notification content',
  `state` VARCHAR(32) NOT NULL DEFAULT 'pending'
    COMMENT 'pending/in_progress/confirmed/failed/unknown/resolved',
  `retry_safe` SMALLINT NOT NULL DEFAULT 1
    COMMENT '1 only when provider send is proven not started',
  `attempt_count` INT NOT NULL DEFAULT 0,
  `lease_token` VARCHAR(64) NULL,
  `lease_until` DATETIME NULL,
  `send_started_at` DATETIME NULL,
  `confirmed_at` DATETIME NULL,
  `provider_success` SMALLINT NULL,
  `provider_status_code` INT NULL,
  `cost_ms` INT NULL,
  `result_code` VARCHAR(64) NULL COMMENT 'delivered/rejected only',
  `log_persisted` SMALLINT NOT NULL DEFAULT 0,
  `last_error_code` VARCHAR(64) NULL,
  `resolved_at` DATETIME NULL,
  `resolution_code` VARCHAR(64) NULL COMMENT 'manual_reconciled only',
  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_notification_test_attempt_key` (`idempotency_key`),
  KEY `idx_notification_test_target_created` (`user_id`, `channel_key`, `created_time`, `id`),
  KEY `idx_notification_test_state_lease` (`state`, `lease_until`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Metadata-only at-most-once notification test attempts';

CREATE TABLE IF NOT EXISTS `notification_test_target_mutex` (
  `user_id` BIGINT NOT NULL,
  `channel_key` VARCHAR(80) NOT NULL,
  `latest_attempt_id` BIGINT NULL,
  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`, `channel_key`),
  KEY `idx_notification_test_target_latest` (`latest_attempt_id`),
  CONSTRAINT `fk_notification_test_target_latest`
    FOREIGN KEY (`latest_attempt_id`) REFERENCES `notification_test_attempt` (`id`)
    ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Per-user/channel mutex for notification test sends';
