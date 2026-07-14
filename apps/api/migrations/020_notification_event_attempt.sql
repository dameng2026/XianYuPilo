-- Migration 020: durable at-most-once generations for automatic event delivery.
-- Both tables are metadata-only. Target identity is an irreversible SHA-256
-- digest; payload text, marketplace identifiers and channel credentials are
-- intentionally excluded.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `notification_event_attempt` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `event_type` VARCHAR(64) NOT NULL,
  `account_id` BIGINT NOT NULL,
  `target_digest` CHAR(64) NOT NULL COMMENT 'SHA-256 identity only',
  `generation` INT NOT NULL,
  `state` VARCHAR(32) NOT NULL DEFAULT 'pending'
    COMMENT 'pending/send_started/confirmed/failed/unknown/resolved/expired',
  `attempt_count` INT NOT NULL DEFAULT 0,
  `lease_token` VARCHAR(64) NULL,
  `lease_until` DATETIME NULL,
  `send_started_at` DATETIME NULL,
  `confirmed_at` DATETIME NULL,
  `generation_expires_at` DATETIME NULL COMMENT 'set only for bounded dedup windows',
  `next_retry_at` DATETIME NULL,
  `provider_called` SMALLINT NULL,
  `delivered` SMALLINT NULL,
  `outcome_known` SMALLINT NULL,
  `last_error_code` VARCHAR(64) NULL,
  `resolved_at` DATETIME NULL,
  `resolution_code` VARCHAR(64) NULL COMMENT 'verified_recovery/explicit_clear',
  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_notification_event_generation`
    (`event_type`, `account_id`, `target_digest`, `generation`),
  KEY `idx_notification_event_target_created`
    (`event_type`, `account_id`, `target_digest`, `created_time`, `id`),
  KEY `idx_notification_event_state_lease` (`state`, `lease_until`),
  KEY `idx_notification_event_retry` (`state`, `next_retry_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Metadata-only automatic notification event generations';

CREATE TABLE IF NOT EXISTS `notification_event_target_mutex` (
  `event_type` VARCHAR(64) NOT NULL,
  `account_id` BIGINT NOT NULL,
  `target_digest` CHAR(64) NOT NULL COMMENT 'SHA-256 identity only',
  `latest_attempt_id` BIGINT NULL,
  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`event_type`, `account_id`, `target_digest`),
  KEY `idx_notification_event_target_latest` (`latest_attempt_id`),
  CONSTRAINT `fk_notification_event_target_latest`
    FOREIGN KEY (`latest_attempt_id`) REFERENCES `notification_event_attempt` (`id`)
    ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Per-event/account/digest mutex for automatic notification delivery';
