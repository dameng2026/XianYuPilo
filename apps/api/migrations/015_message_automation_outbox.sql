-- Migration 015: transactional outbox for post-persistence message automation.
--
-- One inbound chat INSERT and its delivery/AI branch rows are committed in the
-- same database transaction.  The outbox contains no buyer message body: the
-- worker rehydrates the already-authoritative xianyu_chat_message row only
-- after it has obtained a finite lease.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `message_automation_outbox` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `account_id` BIGINT NOT NULL,
  `chat_message_id` BIGINT NOT NULL,
  `source_message_digest` CHAR(64) NOT NULL,
  `branch` VARCHAR(16) NOT NULL COMMENT 'delivery/ai',
  `state` VARCHAR(32) NOT NULL DEFAULT 'pending' COMMENT 'pending/processing/completed/failed/unknown',
  `retry_safe` SMALLINT NOT NULL DEFAULT 1,
  `attempt_count` INT NOT NULL DEFAULT 0,
  `lease_token` VARCHAR(64) NULL,
  `lease_until` DATETIME NULL,
  `next_attempt_at` DATETIME NULL,
  `completed_at` DATETIME NULL,
  `last_error_code` VARCHAR(64) NULL,
  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_message_automation_source_branch` (`account_id`, `source_message_digest`, `branch`),
  UNIQUE KEY `uk_message_automation_message_branch` (`chat_message_id`, `branch`),
  KEY `idx_message_automation_claim` (`state`, `retry_safe`, `next_attempt_at`, `lease_until`),
  KEY `idx_message_automation_account_created` (`account_id`, `created_time`),
  CONSTRAINT `fk_message_automation_chat_message`
    FOREIGN KEY (`chat_message_id`) REFERENCES `xianyu_chat_message` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Inbound message delivery/AI transactional outbox';
