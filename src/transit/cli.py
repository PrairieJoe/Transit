"""Command-line interface for the Transit MVP."""
import argparse
import json
from pathlib import Path

from .db import Database
from .ingest import register_file
from .pipeline import run_network_scenario, run_scenario, summarize_card_demand, summarize_stop_demand
from .metrics import export_geojson

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="transit", description="Transit demand and bus scenario analysis")
    parser.add_argument("--db", default="data/transit.sqlite3", help="SQLite database path")
    commands = parser.add_subparsers(dest="command", required=True)
    dataset = commands.add_parser("dataset")
    dataset_commands = dataset.add_subparsers(dest="dataset_command", required=True)
    register = dataset_commands.add_parser("register")
    register.add_argument("--file", required=True)
    register.add_argument("--type", choices=("card", "bis"), required=True)
    validate = dataset_commands.add_parser("validate")
    validate.add_argument("--dataset", required=True)
    demand = commands.add_parser("demand")
    demand_commands = demand.add_subparsers(dest="demand_command", required=True)
    summarize = demand_commands.add_parser("summarize")
    summarize.add_argument("--dataset", required=True)
    summarize.add_argument("--scope", choices=("route", "stop"), default="route")
    scenario = commands.add_parser("scenario")
    scenario_commands = scenario.add_subparsers(dest="scenario_command", required=True)
    run = scenario_commands.add_parser("run")
    run.add_argument("--file", required=True)
    compare = scenario_commands.add_parser("compare")
    compare.add_argument("--scenario", required=True)
    compare.add_argument("--format", choices=("json", "csv", "geojson"), default="json")
    compare.add_argument("--output")
    compare.add_argument("--network")
    return parser

def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    database = Database(Path(args.db))
    try:
        if args.command == "dataset" and args.dataset_command == "register":
            print(f"dataset_id={register_file(database, args.file, args.type)}")
            return 0
        if args.command == "dataset" and args.dataset_command == "validate":
            row = database.query_one("SELECT id, quality_status FROM datasets WHERE id = ?", (args.dataset,))
            if row is None:
                print(f"error_code=dataset.not_found dataset_id={args.dataset}")
                return 1
            print(f"dataset_id={row[0]} quality_status={row[1]}")
            return 0 if row[1] == "passed" else 1
        if args.command == "demand" and args.demand_command == "summarize":
            summary = summarize_stop_demand(database, args.dataset) if args.scope == "stop" else summarize_card_demand(database, args.dataset)
            print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "scenario" and args.scenario_command == "run":
            payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
            if "journeys" in payload:
                result = run_network_scenario(
                    database, payload["name"], payload["journeys"],
                    payload["base_network"], payload.get("changes", []), payload.get("beta", 0.08),
                )
            else:
                result = run_scenario(
                    database, payload["name"], payload["base_counts"], payload["scenario_counts"],
                    payload.get("base_network"), payload.get("changes"),
                )
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "scenario" and args.scenario_command == "compare":
            rows = database.query_all(
                "SELECT scope_id, base_value, scenario_value, delta_value "
                "FROM metric_results WHERE scenario_id = ? ORDER BY scope_id",
                (args.scenario,),
            )
            if not rows:
                print(f"error_code=scenario.not_found_or_empty scenario_id={args.scenario}")
                return 1
            result = {scope_id: {"base_value": base, "scenario_value": scenario, "delta_value": delta} for scope_id, base, scenario, delta in rows}
            if args.format == "csv":
                from .metrics import export_metrics_csv
                target = Path(args.output or "metrics.csv")
                export_metrics_csv(target, result)
                print(f"output={target}")
            elif args.format == "geojson":
                if not args.network:
                    print("error_code=network.required_for_geojson")
                    return 1
                network = json.loads(Path(args.network).read_text(encoding="utf-8"))
                features = [
                    {"id": route_id, "coordinates": route.get("coordinates", [])}
                    for route_id, route in network.get("routes", {}).items()
                    if route.get("coordinates")
                ]
                target = Path(args.output or "routes.geojson")
                export_geojson(target, features)
                print(f"output={target}")
            else:
                print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0
        return 2
    finally:
        database.close()

if __name__ == "__main__":
    raise SystemExit(main())
