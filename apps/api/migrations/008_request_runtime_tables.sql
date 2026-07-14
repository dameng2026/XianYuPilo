SET NAMES utf8mb4;

-- These tables used to be created lazily by API request handlers. Keep all
-- schema ownership in the numbered migration gate so API/worker identities can
-- run without DDL privileges and a missing migration fails closed at startup.
CREATE TABLE IF NOT EXISTS `user_business_setting` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `user_id` BIGINT NOT NULL DEFAULT 0,
  `setting_key` VARCHAR(100) NOT NULL,
  `config_json` LONGTEXT NOT NULL,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `deleted` TINYINT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uk_user_business_setting_user_key` (`user_id`, `setting_key`),
  INDEX `idx_user_business_setting_key` (`setting_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='User-scoped business settings';

CREATE TABLE IF NOT EXISTS `user_notification_setting` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `user_id` BIGINT NOT NULL,
  `config_json` JSON NOT NULL,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `deleted` TINYINT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uk_uns_user` (`user_id`),
  INDEX `idx_uns_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='User notification settings';

CREATE TABLE IF NOT EXISTS `notification_delivery_log` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `user_id` BIGINT NULL,
  `channel_key` VARCHAR(80) NULL,
  `channel_name` VARCHAR(120) NULL,
  `event_type` VARCHAR(80) NULL,
  `success` TINYINT NULL DEFAULT 0,
  `status_code` INT NULL DEFAULT 0,
  `cost_ms` BIGINT NULL DEFAULT 0,
  `message` VARCHAR(500) NULL,
  `request_body` TEXT NULL,
  `response_body` TEXT NULL,
  `retry_count` INT NULL DEFAULT 0,
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_ndl_user_time` (`user_id`, `created_time`),
  INDEX `idx_ndl_success` (`success`, `created_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Notification delivery log';
