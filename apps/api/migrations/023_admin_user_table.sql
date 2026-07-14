-- Migration 023: admin_user table for email-based admin authentication.
-- Supports email verification code login, registration, and password reset
-- alongside the legacy single-admin password hash setting. Seeds the default
-- super admin from the existing admin_password_hash / admin_username settings
-- when the table is empty so upgrades preserve the configured password.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `admin_user` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `username` VARCHAR(100) NOT NULL,
  `email` VARCHAR(200) NULL,
  `password_hash` VARCHAR(255) NOT NULL,
  `is_super` TINYINT NULL DEFAULT 0 COMMENT '1=超级管理员',
  `status` TINYINT NULL DEFAULT 1 COMMENT '1=启用 0=禁用',
  `created_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uk_admin_user_username` (`username`),
  UNIQUE INDEX `uk_admin_user_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='管理员账号';

-- Seed the default super admin from the legacy admin_password_hash setting
-- only when the new table is empty and a password hash has been configured.
INSERT INTO `admin_user` (`username`, `email`, `password_hash`, `is_super`, `status`)
SELECT
  COALESCE(
    (SELECT `setting_value` FROM `xianyu_sys_setting` WHERE `setting_key` = 'admin_username'),
    'admin'
  ),
  NULL,
  `setting_value`,
  1,
  1
FROM `xianyu_sys_setting`
WHERE `setting_key` = 'admin_password_hash'
  AND `setting_value` IS NOT NULL
  AND `setting_value` != ''
  AND NOT EXISTS (SELECT 1 FROM `admin_user`);
