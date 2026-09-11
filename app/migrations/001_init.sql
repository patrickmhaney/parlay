-- Parlay Syndicate schema.
--
-- Ids are uuid4 strings except games/teams, which use ESPN's own stable ids.
-- Referential integrity is enforced in the repository layer rather than with
-- FK constraints, to keep migrations and bulk backfills straightforward.

CREATE TABLE users (
    id            VARCHAR PRIMARY KEY,
    email         VARCHAR NOT NULL UNIQUE,
    display_name  VARCHAR NOT NULL,
    phone         VARCHAR,
    created_at    TIMESTAMP NOT NULL,
    last_login_at TIMESTAMP
);

CREATE TABLE syndicates (
    id              VARCHAR PRIMARY KEY,
    name            VARCHAR NOT NULL,
    slug            VARCHAR NOT NULL UNIQUE,
    owner_id        VARCHAR NOT NULL,
    juice_odds      INTEGER NOT NULL DEFAULT -110,
    lock_at_kickoff BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP NOT NULL
);

CREATE TABLE memberships (
    syndicate_id VARCHAR NOT NULL,
    user_id      VARCHAR NOT NULL,
    role         VARCHAR NOT NULL DEFAULT 'member',
    joined_at    TIMESTAMP NOT NULL,
    PRIMARY KEY (syndicate_id, user_id)
);

CREATE TABLE invites (
    id           VARCHAR PRIMARY KEY,
    syndicate_id VARCHAR NOT NULL,
    email        VARCHAR,
    token_hash   VARCHAR NOT NULL UNIQUE,
    invited_by   VARCHAR,
    created_at   TIMESTAMP NOT NULL,
    expires_at   TIMESTAMP NOT NULL,
    accepted_at  TIMESTAMP,
    accepted_by  VARCHAR
);

-- Single-use magic-link tokens. Only the hash is ever stored.
CREATE TABLE login_tokens (
    token_hash  VARCHAR PRIMARY KEY,
    email       VARCHAR NOT NULL,
    created_at  TIMESTAMP NOT NULL,
    expires_at  TIMESTAMP NOT NULL,
    consumed_at TIMESTAMP,
    redirect_to VARCHAR
);

CREATE TABLE sessions (
    token_hash   VARCHAR PRIMARY KEY,
    user_id      VARCHAR NOT NULL,
    created_at   TIMESTAMP NOT NULL,
    expires_at   TIMESTAMP NOT NULL,
    last_seen_at TIMESTAMP NOT NULL
);

CREATE TABLE teams (
    id           VARCHAR PRIMARY KEY,   -- ESPN team id
    abbreviation VARCHAR NOT NULL,
    display_name VARCHAR NOT NULL,
    short_name   VARCHAR,
    location     VARCHAR,
    color        VARCHAR,
    logo_url     VARCHAR
);

CREATE TABLE games (
    id               VARCHAR PRIMARY KEY,  -- ESPN event id
    season           INTEGER NOT NULL,
    season_type      INTEGER NOT NULL DEFAULT 2,
    week             INTEGER NOT NULL,
    kickoff_at       TIMESTAMP,
    home_team_id     VARCHAR NOT NULL,
    away_team_id     VARCHAR NOT NULL,
    home_score       INTEGER,
    away_score       INTEGER,
    status           VARCHAR NOT NULL,
    completed        BOOLEAN NOT NULL DEFAULT FALSE,
    favorite_team_id VARCHAR,
    spread           DECIMAL(5,1),         -- favorite's number (negative)
    over_under       DECIMAL(5,1),
    odds_provider    VARCHAR,
    synced_at        TIMESTAMP NOT NULL
);

CREATE INDEX idx_games_season_week ON games (season, week);

CREATE TABLE picks (
    id           VARCHAR PRIMARY KEY,
    syndicate_id VARCHAR NOT NULL,
    user_id      VARCHAR NOT NULL,
    game_id      VARCHAR NOT NULL,
    season       INTEGER NOT NULL,
    week         INTEGER NOT NULL,
    bet_type     VARCHAR NOT NULL,      -- SPREAD | OVER | UNDER
    side_team_id VARCHAR,               -- SPREAD only
    line         DECIMAL(5,1) NOT NULL,
    created_at   TIMESTAMP NOT NULL,
    updated_at   TIMESTAMP NOT NULL,
    source       VARCHAR NOT NULL DEFAULT 'app',
    UNIQUE (syndicate_id, user_id, season, week)
);

CREATE INDEX idx_picks_week ON picks (syndicate_id, season, week);

CREATE TABLE pick_results (
    pick_id         VARCHAR PRIMARY KEY,
    outcome         VARCHAR NOT NULL,   -- WIN | LOSS | PUSH
    margin          DECIMAL(6,1) NOT NULL,
    graded_at       TIMESTAMP NOT NULL,
    manual_override BOOLEAN NOT NULL DEFAULT FALSE,
    note            VARCHAR
);

CREATE TABLE notifications (
    id           VARCHAR PRIMARY KEY,
    syndicate_id VARCHAR,
    kind         VARCHAR NOT NULL,   -- picks_in | results | login | invite
    channel      VARCHAR NOT NULL,   -- sms | email
    recipient    VARCHAR NOT NULL,
    body         VARCHAR,
    status       VARCHAR NOT NULL,   -- sent | failed | skipped
    error        VARCHAR,
    created_at   TIMESTAMP NOT NULL
);

-- Marks a (syndicate, season, week) board as locked and notified, so the
-- "picks are in" text fires exactly once regardless of retries.
CREATE TABLE week_locks (
    syndicate_id VARCHAR NOT NULL,
    season       INTEGER NOT NULL,
    week         INTEGER NOT NULL,
    locked_at    TIMESTAMP NOT NULL,
    notified_at  TIMESTAMP,
    PRIMARY KEY (syndicate_id, season, week)
);
