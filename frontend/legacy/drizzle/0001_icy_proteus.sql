DROP INDEX `appointments_slot_unique`;--> statement-breakpoint
CREATE UNIQUE INDEX `appointments_active_slot_unique` ON `appointments` (`slot`) WHERE status IN ('provisional','confirmed');--> statement-breakpoint
ALTER TABLE `requests` ADD `updated_at` text;--> statement-breakpoint
ALTER TABLE `requests` ADD `internal_note` text DEFAULT '' NOT NULL;