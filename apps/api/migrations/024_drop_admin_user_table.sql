-- Migration 024: Drop admin_user table (revert email-based auth).
-- The open-source edition returns to single-admin mode (admin/123456 from
-- .env ADMIN_USERNAME / ADMIN_PASSWORD_HASH) and no longer needs the table.

DROP TABLE IF EXISTS `admin_user`;
