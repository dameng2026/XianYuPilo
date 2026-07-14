-- Migration 025: Recreate admin_user table for email-based admin authentication.
-- Reverts migration 024 (which dropped the table to return to single-admin mode).
-- The open-source edition now supports email verification code login, registration
-- and password reset alongside the legacy .env-based admin/123456 credentials.
-- Seeds the default super admin with the bcrypt hash of "123456" (matching the
-- default ADMIN_PASSWORD_HASH shipped in .env) when the table is empty, so
-- upgrades preserve the configured password without requiring a separate step.

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

-- Seed the default super admin (admin/123456) only when the table is empty.
-- The password hash matches .env ADMIN_PASSWORD_HASH default so the legacy
-- username/password login and the new email login share the same credentials.
INSERT INTO `admin_user` (`username`, `email`, `password_hash`, `is_super`, `status`)
SELECT
  'admin',
  NULL,
  '$2b$12$1utcQmOqD6kTYaMEIpr3xugyt.UzbERTorb8KvssYRLSzDfEvhwlK',
  1,
  1
WHERE NOT EXISTS (SELECT 1 FROM `admin_user`);
