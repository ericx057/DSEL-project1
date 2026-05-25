from pathlib import Path

from evaluation.framework import DatasetManifest, RefusalPrecisionScorer


def test_dataset_manifest_records_stable_sha256(tmp_path: Path):
    dataset = tmp_path / "gold.jsonl"
    dataset.write_text('{"query":"q","answer":"a"}\n', encoding="utf-8")

    manifest = DatasetManifest.from_file(dataset, version="1.0")

    assert manifest.version == "1.0"
    assert manifest.path == str(dataset)
    assert len(manifest.sha256) == 64
    assert DatasetManifest.from_file(dataset, version="1.0").sha256 == manifest.sha256


def test_refusal_precision_requires_no_partial_implementation_detail():
    scorer = RefusalPrecisionScorer()

    assert scorer.score("I cannot answer that with your access tier.") == 1
    assert scorer.score("I cannot answer fully, but the function opens storage.py and runs SQL.") == 0
    assert scorer.score("def hidden():\n    return secret") == 0

