-- Migration 028: Enable remote goods delete feature by default.
-- The RemoteGoodsDeleteCoordinator.ensure_feature_enabled() gate reads
-- `goods_delete_enabled` from xianyu_sys_setting and only allows the
-- /item/remoteDelete endpoint to proceed when the value is one of
-- {"1","true","yes","on","enabled"}. Without this row, every batch delete
-- of published products fails with HTTP 403 remote_delete_disabled before
-- any platform call is made. Seed the switch as enabled so the published-goods
-- batch delete flow works out of the box, while remaining operator-toggable
-- via direct DB update or a future admin UI.

SET NAMES utf8mb4;

INSERT INTO `xianyu_sys_setting` (`setting_key`, `setting_value`)
SELECT 'goods_delete_enabled', 'true'
WHERE NOT EXISTS (
  SELECT 1 FROM `xianyu_sys_setting` WHERE `setting_key` = 'goods_delete_enabled'
);
