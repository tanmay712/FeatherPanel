-- OrveX VPS Nodes (vps-node/ in this repository): the panel's own VPS node system.
-- node_type tells OrveX nodes apart from Proxmox nodes. An OrveX node is created
-- in the panel first and connects itself with a one-time registration token; the
-- agent details it reports are kept in agent_info (JSON).
-- Guarded so the migration is safe to re-run on MySQL 8 / MariaDB.
SET @fp_sql = IF(
	(SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'featherpanel_vm_nodes' AND COLUMN_NAME = 'node_type') = 0,
	'ALTER TABLE `featherpanel_vm_nodes` ADD COLUMN `node_type` VARCHAR(20) NOT NULL DEFAULT ''proxmox'' AFTER `location_id`',
	'SELECT 1'
);
PREPARE fp_stmt FROM @fp_sql;
EXECUTE fp_stmt;
DEALLOCATE PREPARE fp_stmt;

SET @fp_sql = IF(
	(SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'featherpanel_vm_nodes' AND COLUMN_NAME = 'registration_token') = 0,
	'ALTER TABLE `featherpanel_vm_nodes` ADD COLUMN `registration_token` TEXT NULL DEFAULT NULL',
	'SELECT 1'
);
PREPARE fp_stmt FROM @fp_sql;
EXECUTE fp_stmt;
DEALLOCATE PREPARE fp_stmt;

SET @fp_sql = IF(
	(SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'featherpanel_vm_nodes' AND COLUMN_NAME = 'registration_expires_at') = 0,
	'ALTER TABLE `featherpanel_vm_nodes` ADD COLUMN `registration_expires_at` DATETIME NULL DEFAULT NULL',
	'SELECT 1'
);
PREPARE fp_stmt FROM @fp_sql;
EXECUTE fp_stmt;
DEALLOCATE PREPARE fp_stmt;

SET @fp_sql = IF(
	(SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'featherpanel_vm_nodes' AND COLUMN_NAME = 'registered_at') = 0,
	'ALTER TABLE `featherpanel_vm_nodes` ADD COLUMN `registered_at` DATETIME NULL DEFAULT NULL',
	'SELECT 1'
);
PREPARE fp_stmt FROM @fp_sql;
EXECUTE fp_stmt;
DEALLOCATE PREPARE fp_stmt;

SET @fp_sql = IF(
	(SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'featherpanel_vm_nodes' AND COLUMN_NAME = 'agent_version') = 0,
	'ALTER TABLE `featherpanel_vm_nodes` ADD COLUMN `agent_version` VARCHAR(32) NULL DEFAULT NULL',
	'SELECT 1'
);
PREPARE fp_stmt FROM @fp_sql;
EXECUTE fp_stmt;
DEALLOCATE PREPARE fp_stmt;

SET @fp_sql = IF(
	(SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'featherpanel_vm_nodes' AND COLUMN_NAME = 'agent_info') = 0,
	'ALTER TABLE `featherpanel_vm_nodes` ADD COLUMN `agent_info` MEDIUMTEXT NULL DEFAULT NULL',
	'SELECT 1'
);
PREPARE fp_stmt FROM @fp_sql;
EXECUTE fp_stmt;
DEALLOCATE PREPARE fp_stmt;

-- OrveX nodes that were added by hand before this migration (API user in the @orvex realm).
UPDATE `featherpanel_vm_nodes`
	SET `node_type` = 'orvex', `registered_at` = COALESCE(`registered_at`, `created_at`)
	WHERE `user` LIKE '%@orvex';
