"""SQLite persistence for Transit MVP."""
import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS datasets (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, source_type TEXT NOT NULL,
  file_path TEXT NOT NULL, file_hash TEXT NOT NULL UNIQUE, schema_version TEXT NOT NULL,
  quality_status TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stops (
  id TEXT PRIMARY KEY, source_dataset_id TEXT NOT NULL, source_stop_id TEXT NOT NULL,
  name TEXT NOT NULL, latitude REAL NOT NULL, longitude REAL NOT NULL,
  canonical_status TEXT NOT NULL, FOREIGN KEY (source_dataset_id) REFERENCES datasets(id)
);
CREATE TABLE IF NOT EXISTS routes (
  id TEXT PRIMARY KEY, source_dataset_id TEXT NOT NULL, source_route_id TEXT NOT NULL,
  name TEXT NOT NULL, direction TEXT, canonical_status TEXT NOT NULL,
  FOREIGN KEY (source_dataset_id) REFERENCES datasets(id)
);
CREATE TABLE IF NOT EXISTS route_stops (
  route_id TEXT NOT NULL, stop_id TEXT NOT NULL, stop_sequence INTEGER NOT NULL,
  distance_m REAL, travel_time_s REAL, source_type TEXT NOT NULL,
  PRIMARY KEY (route_id, stop_sequence),
  FOREIGN KEY (route_id) REFERENCES routes(id), FOREIGN KEY (stop_id) REFERENCES stops(id)
);
CREATE TABLE IF NOT EXISTS card_transactions (
  id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL, transaction_time TEXT NOT NULL,
  journey_key TEXT, route_id TEXT, boarding_stop_id TEXT, alighting_stop_id TEXT,
  transfer_group_id TEXT, transaction_type TEXT NOT NULL, alighting_status TEXT NOT NULL,
  FOREIGN KEY (dataset_id) REFERENCES datasets(id)
);
CREATE TABLE IF NOT EXISTS journeys (
  id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL, boarding_time TEXT NOT NULL,
  origin_stop_id TEXT NOT NULL, destination_stop_id TEXT, destination_status TEXT NOT NULL,
  weight REAL NOT NULL DEFAULT 1.0, FOREIGN KEY (dataset_id) REFERENCES datasets(id)
);
CREATE TABLE IF NOT EXISTS scenarios (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, base_network_version TEXT NOT NULL,
  status TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scenario_changes (
  id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, change_type TEXT NOT NULL,
  payload_json TEXT NOT NULL, FOREIGN KEY (scenario_id) REFERENCES scenarios(id)
);
CREATE TABLE IF NOT EXISTS metric_results (
  id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, scope_type TEXT NOT NULL,
  scope_id TEXT NOT NULL, metric_name TEXT NOT NULL, base_value REAL,
  scenario_value REAL, delta_value REAL, created_at TEXT NOT NULL
);
"""

class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(SCHEMA)
        self.connection.commit()

    def execute(self, sql: str, parameters: tuple = ()) -> sqlite3.Cursor:
        cursor = self.connection.execute(sql, parameters)
        self.connection.commit()
        return cursor

    def query_one(self, sql: str, parameters: tuple = ()):
        return self.connection.execute(sql, parameters).fetchone()

    def query_all(self, sql: str, parameters: tuple = ()):
        return self.connection.execute(sql, parameters).fetchall()

    def close(self) -> None:
        self.connection.close()

