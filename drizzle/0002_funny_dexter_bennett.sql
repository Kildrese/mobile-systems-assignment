-- Existing users get a username derived from their email: the local part
-- stripped to allowed characters (letters, digits, `_`, `.`), lowercased,
-- plus `_` and the first 10 hex digits of their id so it is unique. At most
-- 19 + 1 + 10 = 30 characters, the username maximum.
ALTER TABLE "user" ADD COLUMN "username" text;--> statement-breakpoint
UPDATE "user" SET "username" = lower(left(regexp_replace(split_part("email", '@', 1), '[^a-zA-Z0-9_.]', '', 'g'), 19)) || '_' || left(replace("id"::text, '-', ''), 10);--> statement-breakpoint
ALTER TABLE "user" ALTER COLUMN "username" SET NOT NULL;--> statement-breakpoint
ALTER TABLE "user" ADD CONSTRAINT "user_username_unique" UNIQUE("username");
