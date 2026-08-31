import csv
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_sample_dataset_meets_mvp_minimums():
    bis_rows = list(csv.DictReader((ROOT / "data/sample/bis.csv").open(encoding="utf-8")))
    card_rows = list(csv.DictReader((ROOT / "data/sample/cards.csv").open(encoding="utf-8")))

    assert len({row["route_id"] for row in bis_rows}) >= 2
    assert len({row["stop_id"] for row in bis_rows}) >= 20
    assert len(card_rows) >= 200
