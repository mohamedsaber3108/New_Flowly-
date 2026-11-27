CREATE TABLE `request_events` (
  `id` text PRIMARY KEY NOT NULL,
  `request_id` text NOT NULL,
  `event_type` text NOT NULL,
  `status` text,
  `created_at` text NOT NULL,
  FOREIGN KEY (`request_id`) REFERENCES `requests`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `request_events_request_created_idx` ON `request_events` (`request_id`,`created_at`);
