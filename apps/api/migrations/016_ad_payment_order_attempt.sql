-- Migration 016: durable exactly-once state for commercial ad payment orders.
-- A separate row per commercial application is the business-target mutex,
-- while immutable attempt generations retain audit/replay history.  Neither
-- table stores contact data, bridge response bodies, pay URLs, QR payloads,
-- credentials, or other payment secrets.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `ad_payment_order_target_mutex` (
  `application_id` BIGINT NOT NULL COMMENT '商业广告申请 ID；跨代支付意图互斥键',
  `latest_attempt_id` BIGINT NULL COMMENT '当前代 attempt；由事务内目标锁保护',
  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`application_id`),
  KEY `idx_ad_payment_target_latest` (`latest_attempt_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='商业广告支付订单目标互斥';

CREATE TABLE IF NOT EXISTS `ad_payment_order_attempt` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `application_id` BIGINT NOT NULL COMMENT '商业广告申请 ID；同时作为目标互斥键',
  `idempotency_key` VARCHAR(128) NOT NULL COMMENT '必须原样透传商业桥的支付意图键',
  `payload_digest` CHAR(64) NOT NULL COMMENT 'application_id 与 payment_method 的 SHA-256',
  `payment_method` VARCHAR(64) NOT NULL,
  `state` VARCHAR(32) NOT NULL DEFAULT 'pending'
    COMMENT 'pending/in_progress/confirmed/failed/unknown/closed/expired',
  `retry_safe` SMALLINT NOT NULL DEFAULT 1 COMMENT '仅明确未向商业桥发出请求时为 1',
  `attempt_count` INT NOT NULL DEFAULT 0,
  `lease_token` VARCHAR(64) NULL,
  `lease_until` DATETIME NULL,
  `remote_started_at` DATETIME NULL,
  `remote_confirmed_at` DATETIME NULL,
  `remote_order_no` VARCHAR(128) NULL COMMENT '最小核对引用；不保存二维码或支付链接',
  `remote_status` VARCHAR(32) NULL,
  `last_error_code` VARCHAR(64) NULL,
  `error_message` VARCHAR(500) NULL COMMENT '固定、脱敏、限长的用户可操作错误',
  `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ad_payment_order_attempt_key` (`idempotency_key`),
  UNIQUE KEY `uk_ad_payment_order_attempt_remote_order` (`remote_order_no`),
  KEY `idx_ad_payment_order_application_created` (`application_id`, `created_time`, `id`),
  KEY `idx_ad_payment_order_state_lease` (`state`, `lease_until`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='商业广告支付订单持久化幂等状态';
