-- Free servers: which servers were created through the free tier, the stack the user picked,
-- and where each one is in the inactivity flow (running, stopped after the first period
-- without a login, in storage after the second). Rows go away with their server.
CREATE TABLE IF NOT EXISTS `featherpanel_free_servers` (
	`id` INT(11) NOT NULL AUTO_INCREMENT,
	`server_id` INT(11) NOT NULL,
	`stack` VARCHAR(32) NOT NULL,
	`stage` VARCHAR(16) DEFAULT NULL,
	`stage_at` DATETIME DEFAULT NULL,
	`restored_at` DATETIME DEFAULT NULL,
	`created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (`id`),
	UNIQUE KEY `free_servers_server_id_unique` (`server_id`),
	KEY `free_servers_stage_index` (`stage`),
	CONSTRAINT `free_servers_server_id_foreign` FOREIGN KEY (`server_id`) REFERENCES `featherpanel_servers` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
