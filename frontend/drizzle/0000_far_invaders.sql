CREATE TABLE `appointments` (
	`id` text PRIMARY KEY NOT NULL,
	`request_id` text NOT NULL,
	`slot` text NOT NULL,
	`date` text NOT NULL,
	`time` text NOT NULL,
	`timezone` text DEFAULT 'Africa/Cairo' NOT NULL,
	`status` text DEFAULT 'provisional' NOT NULL,
	FOREIGN KEY (`request_id`) REFERENCES `requests`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE UNIQUE INDEX `appointments_slot_unique` ON `appointments` (`slot`);--> statement-breakpoint
CREATE INDEX `appointments_date_idx` ON `appointments` (`date`);--> statement-breakpoint
CREATE TABLE `rate_limits` (
	`key` text PRIMARY KEY NOT NULL,
	`hits` integer DEFAULT 0 NOT NULL,
	`expires` integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE `requests` (
	`id` text PRIMARY KEY NOT NULL,
	`reference` text NOT NULL,
	`kind` text NOT NULL,
	`audience` text NOT NULL,
	`name` text NOT NULL,
	`email` text NOT NULL,
	`organization` text NOT NULL,
	`details` text NOT NULL,
	`status` text DEFAULT 'pending_review' NOT NULL,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `requests_reference_unique` ON `requests` (`reference`);