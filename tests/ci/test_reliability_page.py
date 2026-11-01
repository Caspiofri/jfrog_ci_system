"""The reliability review page on the labeling server: every field of a review file's items, each mark saved on the
server, competitor / category / score marks mirrored into the review file's answers. Offline."""
import json

import pytest
import yaml
from fastapi.testclient import TestClient

from ci import reliability
from ci.labeling.app import create_app
from tests.ci.test_reliability import MORNING, store  # noqa: F401  (the fixture)


@pytest.fixture
def review(store, tmp_path):  # noqa: F811
    reviews = tmp_path / "reviews"
    path = reliability.make(store_path=store, out_dir=reviews, now=MORNING)
    app = create_app(runs_dir=tmp_path / "runs", labels_path=tmp_path / "l.jsonl", competitors=[],
                     reviews_dir=reviews, store_path=store)
    return TestClient(app), path, yaml.safe_load(path.read_text())["run_id"]


def test_the_sheet_lists_the_review_files_items_with_every_field(review):
    client, path, run = review
    assert client.get("/api/reliability").json()["runs"] == [run]
    d = client.get(f"/api/reliability/{run}").json()
    assert (d["held"], d["auto"], d["seed"]) == (1, 20, reliability.SEED)
    assert [x["id"] for x in d["items"]] == [x["id"] for x in yaml.safe_load(path.read_text())["items"]]
    held = d["items"][0]
    assert [f["key"] for f in held["fields"]] == list(reliability.FIELD_KEYS)
    values = {f["key"]: f["value"] for f in held["fields"]}
    assert values["competitor"] == "github" and values["noise"] == "no"
    assert values["vetted"].startswith("not vetted") and "unvetted_source" in values["routing"]
    assert d["marks"] == {}
    assert client.get("/reliability").status_code == 200


def test_a_mark_is_saved_on_the_server_and_mirrored_into_the_answers(review):
    client, path, run = review
    header = path.read_text().split("run_id:")[0]
    r = client.put(f"/api/reliability/{run}/marks", json={"item_id": "held1", "field": "category", "mark": "wrong",
                                                         "note": "it is AI & Agents"})
    assert r.status_code == 200 and r.json()["mark"] == "wrong"
    client.put(f"/api/reliability/{run}/marks", json={"item_id": "held1", "field": "lens_axis", "mark": "right"})
    marks = json.loads(reliability.marks_path(path).read_text())["marks"]["held1"]
    assert marks["category"]["note"] == "it is AI & Agents" and marks["lens_axis"]["mark"] == "right"
    assert client.get(f"/api/reliability/{run}").json()["marks"]["held1"]["category"]["mark"] == "wrong"
    data = yaml.safe_load(path.read_text())
    held = next(x for x in data["items"] if x["id"] == "held1")
    assert held["answer"] == {"competitor": None, "category": "wrong", "score": None}  # lens_axis is not an answer
    assert path.read_text().startswith(header)  # the instructions header survives the rewrite
    assert reliability.score(path)["groups"]["held"]["category"]["wrong"] == 1
    client.put(f"/api/reliability/{run}/marks", json={"item_id": "held1", "field": "category", "mark": None})
    held = next(x for x in yaml.safe_load(path.read_text())["items"] if x["id"] == "held1")
    assert held["answer"]["category"] is None


def test_bad_marks_are_refused(review):
    client, _, run = review
    url = f"/api/reliability/{run}/marks"
    assert client.put(url, json={"item_id": "held1", "field": "category", "mark": "maybe"}).status_code == 422
    assert client.put(url, json={"item_id": "held1", "field": "colour", "mark": "right"}).status_code == 422
    assert client.put(url, json={"item_id": "nope", "field": "score", "mark": "right"}).status_code == 422
    assert client.get("/api/reliability/..%2Fsecret").status_code == 404


def test_export_has_one_row_per_item_and_field(review):
    client, _, run = review
    client.put(f"/api/reliability/{run}/marks", json={"item_id": "held1", "field": "score", "mark": "right"})
    rows = client.get(f"/api/reliability/{run}/export").json()["marks"]
    assert len(rows) == 21 * len(reliability.FIELD_KEYS)
    assert [r["mark"] for r in rows if r["item_id"] == "held1" and r["field"] == "score"] == ["right"]
