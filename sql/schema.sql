CREATE TABLE event_types (
    type_id   INTEGER PRIMARY KEY,
    type_name TEXT NOT NULL UNIQUE
);

CREATE TABLE languages (
    language_id   INTEGER PRIMARY KEY,
    language_name TEXT NOT NULL UNIQUE
);

CREATE TABLE actors (
    actor_id INTEGER PRIMARY KEY,
    login    TEXT NOT NULL
);

CREATE TABLE repos (
    repo_id     INTEGER PRIMARY KEY,
    repo_name   TEXT NOT NULL,
    language_id INTEGER REFERENCES languages(language_id)
);

CREATE TABLE events (
    event_id   INTEGER PRIMARY KEY,
    type_id    INTEGER NOT NULL REFERENCES event_types(type_id),
    action     TEXT,
    actor_id   INTEGER REFERENCES actors(actor_id),
    repo_id    INTEGER REFERENCES repos(repo_id),
    created_at TEXT NOT NULL
);