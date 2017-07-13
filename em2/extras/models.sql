DROP SCHEMA public CASCADE;
CREATE SCHEMA public;

-- TODO could store platforms here instead of in redis

CREATE TABLE recipients (
  id SERIAL PRIMARY KEY,
  address VARCHAR(255) NOT NULL UNIQUE
  -- TODO perhaps display name
);
CREATE INDEX recipient_address ON recipients USING btree (address);

CREATE TABLE conversations (
  id SERIAL PRIMARY KEY,
  key VARCHAR(64) UNIQUE,
  published BOOL DEFAULT False,
  creator INT NOT NULL REFERENCES recipients ON DELETE RESTRICT,
  timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  subject VARCHAR(255) NOT NULL,
  -- TODO expiry
  ref VARCHAR (255)
);

CREATE TABLE participants (
  id SERIAL PRIMARY KEY,
  conv INT NOT NULL REFERENCES conversations ON DELETE CASCADE,
  recipient INT NOT NULL REFERENCES recipients ON DELETE RESTRICT,
  readall BOOLEAN DEFAULT FALSE,
  active BOOLEAN DEFAULT TRUE,
  -- TODO permissions, hidden, status
  UNIQUE (conv, recipient)
);

-- see core.Relationships enum which matches this
CREATE TYPE RELATIONSHIP AS ENUM ('sibling', 'child');

CREATE TABLE messages (
  id SERIAL PRIMARY KEY,
  key CHAR(20) NOT NULL,
  conv INT NOT NULL REFERENCES conversations ON DELETE CASCADE,
  after INT REFERENCES messages,
  relationship RELATIONSHIP, -- TODO perhaps record depth to limit child replies
  active BOOLEAN DEFAULT TRUE,
  body TEXT,
  UNIQUE (conv, key)
  -- TODO deleted
);
CREATE INDEX message_key ON messages USING btree (key);

-- see core.Verbs enum which matches this
CREATE TYPE VERB AS ENUM ('add', 'modify', 'delete', 'recover', 'lock', 'unlock');
-- see core.Components enum which matches this
CREATE TYPE COMPONENT AS ENUM ('subject', 'expiry', 'label', 'message', 'participant', 'attachment');

CREATE TABLE actions (
  id SERIAL PRIMARY KEY,
  key CHAR(20) NOT NULL,
  conv INT NOT NULL REFERENCES conversations ON DELETE CASCADE,
  verb VERB NOT NULL,
  component COMPONENT NOT NULL,
  actor INT NOT NULL REFERENCES participants ON DELETE RESTRICT,
  timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  parent INT REFERENCES actions,
  part INT REFERENCES participants,
  message INT REFERENCES messages,
  body TEXT,
  UNIQUE (conv, key)
);
CREATE INDEX action_key ON actions USING btree (key);

CREATE TYPE ACTION_STATUS AS ENUM ('pending', 'temporary_failure', 'failed', 'successful');

CREATE TABLE actions_status (
  action INT NOT NULL REFERENCES actions ON DELETE CASCADE,
  status ACTION_STATUS NOT NULL DEFAULT 'pending',
  platform VARCHAR(265),
  part INT REFERENCES participants,
  errors JSONB[]
);

-- TODO attachments