CREATE TABLE IF NOT EXISTS words (
user_id BIGINT,
guild_id BIGINT,
word TEXT
);

CREATE TABLE IF NOT EXISTS settings (
user_id BIGINT PRIMARY KEY,
disabled BOOL,
blocked_users BIGINT ARRAY,
blocked_channels BIGINT ARRAY
);

CREATE TABLE IF NOT EXISTS timers (
id SERIAL PRIMARY KEY,
user_id BIGINT,
event TEXT,
time TIMESTAMP,
extra jsonb DEFAULT ('{}'::jsonb),
created_at TIMESTAMP DEFAULT (now() at time zone 'utc')
);

CREATE TABLE IF NOT EXISTS highlights (
guild_id BIGINT,
channel_id BIGINT,
message_id BIGINT,
author_id BIGINT,
user_id BIGINT,
word TEXT,
invoked_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS unique_words_index ON words (user_id, guild_id, word);
