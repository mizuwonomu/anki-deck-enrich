"""Original, fabricated records shared by the public regression suite and demo."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


INPUTS = [
    {"id": "demo-001", "expression": "試作重複語", "reading": "しさくじゅうふくご", "meaning_vi": "nghĩa kiểm thử một"},
    {"id": "demo-002", "expression": "霧環", "reading": "きりわ", "meaning_vi": "vòng sương giả lập"},
    {"id": "demo-003", "expression": "星綴", "reading": "ほしつづり", "meaning_vi": "dệt sao giả lập"},
    {"id": "demo-004", "expression": "試作重複語", "reading": "しさくじゅうふくご", "meaning_vi": "nghĩa kiểm thử bốn"},
    {"id": "demo-005", "expression": "波標", "reading": "なみしるべ", "meaning_vi": "dấu sóng giả lập"},
]


def _source(source_id: str, *, pointer: str) -> list[dict[str, str]]:
    return [{"source_id": source_id, "claim_path": pointer}]


def _dictionary(input_id: str) -> dict[str, Any]:
    number = input_id[-3:]
    source_id = f"src-{number}"
    return {
        "source_id": source_id,
        "provider": "jmdict",
        "underlying_source": "Synthetic test data; no external lookup.",
        "url": f"https://example.test/dictionary/entry-{number}",
        "locator": f"synthetic-only/{input_id}",
        "accessed_on": "2026-01-01",
        "observation": "Fabricated only for deterministic software tests; not a dictionary observation.",
        "attribution": None,
        "license": None,
    }


def enriched_records() -> list[dict[str, Any]]:
    """Return independently fabricated schema-valid output, never copied from a delivery."""
    rows: list[dict[str, Any]] = []
    expressions = {row["id"]: row["expression"] for row in INPUTS}
    readings = {row["id"]: row["reading"] for row in INPUTS}
    for index, input_id in enumerate((row["id"] for row in INPUTS), start=1):
        source_id = f"src-{index:03d}"
        sense_ids = [f"sense-{index:03d}-one"]
        if input_id == "demo-001":
            sense_ids.append("sense-001-two")
        senses = []
        for sense_index, sense_id in enumerate(sense_ids):
            label = "A" if sense_index == 0 else "B"
            senses.append({
                "sense_id": sense_id,
                "meaning_vi": f"Nghĩa giả lập {label} của mục {index}.",
                "explanation_vi": f"Giải thích kiểm thử {label} dành riêng cho mục {index}.",
                "evidence_refs": _source(source_id, pointer=f"/senses/{sense_index}/meaning_vi"),
            })

        examples: list[dict[str, Any]] = []
        example_count = 2 if input_id == "demo-001" else 1
        for example_index in range(example_count):
            examples.append({
                "example_id": f"example-{index:03d}-{example_index + 1}",
                "sense_id": sense_ids[-1] if input_id == "demo-001" else sense_ids[0],
                "sentence_ja": f"{expressions[input_id]}を試す{'' if example_index == 0 else '。'}" if example_index == 0 else f"{expressions[input_id]}が残る。",
                "reading": f"{readings[input_id]}をためす。" if example_index == 0 else f"{readings[input_id]}がのこる。",
                "translation_vi": f"Câu kiểm thử {index}-{example_index + 1}.",
                "origin": "generated",
                "origin_source_ids": [],
                "evidence_refs": _source(source_id, pointer=f"/examples/{example_index}/sentence_ja"),
            })

        collocation_count = 2 if input_id in {"demo-001", "demo-002"} else 1
        collocations = []
        for collocation_index in range(collocation_count):
            collocations.append({
                "collocation_id": f"collocation-{index:03d}-{collocation_index + 1}",
                "sense_id": sense_ids[-1] if input_id == "demo-001" else sense_ids[0],
                "expression": f"{expressions[input_id]}を試す" if collocation_index == 0 else f"{expressions[input_id]}が残る",
                "reading": f"{readings[input_id]}をためす",
                "meaning_vi": f"cụm kiểm thử {index}-{collocation_index + 1}",
                "usage_vi": f"ngữ cảnh giả lập {index}-{collocation_index + 1}",
                "frequency": None if collocation_index == 0 else {
                    "count": 3, "corpus": "Synthetic corpus", "query": f"test-{index}", "source_id": source_id,
                },
                "evidence_refs": _source(source_id, pointer=f"/collocations/{collocation_index}/expression"),
            })

        related_terms: list[dict[str, Any]] = []
        if input_id in {"demo-002", "demo-003"}:
            related_terms.append({
                "relation_id": f"relation-{index:03d}", "sense_id": sense_ids[0],
                "expression": "試作近縁語", "reading": "しさくきんえんご", "relationship": "related",
                "note_vi": "Quan hệ chỉ tồn tại trong dữ liệu giả lập; không xác nhận tính thay thế.",
                "evidence_refs": _source(source_id, pointer=f"/related_terms/0/expression"),
            })

        confusables: list[dict[str, Any]] = []
        if input_id == "demo-003":
            confusables.append({
                "confusable_id": "confusable-003", "sense_id": sense_ids[0],
                "expression": "星綴り", "reading": "ほしつづり",
                "distinction_vi": "Cặp đối chiếu giả lập dành cho kiểm thử.",
                "contrast_examples": [{
                    "sentence_ja": "星綴と星綴りは試作例です。", "reading": "ほしつづりとほしつづりはしさくれいです。",
                    "translation_vi": "Đây là ví dụ đối chiếu giả lập.", "origin": "generated",
                    "origin_source_ids": [], "evidence_refs": [],
                }],
                "evidence_refs": _source(source_id, pointer="/confusables/0/distinction_vi"),
            })

        uncertainties = []
        if input_id == "demo-001":
            uncertainties = [
                {"path": "/senses/0/explanation_vi", "issue_vi": "Ghi chú giả lập A, không đưa vào nội dung học."},
                {"path": "/senses/1/explanation_vi", "issue_vi": "Ghi chú giả lập B, không đưa vào nội dung học."},
            ]
        rows.append({
            "schema_version": "0.1.0", "input_id": input_id,
            "revision": 1,
            "headword": {
                "expression": expressions[input_id], "reading": readings[input_id], "pos": ["danh từ giả lập"],
                "evidence_refs": _source(source_id, pointer="/headword/expression"),
            },
            "senses": senses, "examples": examples, "collocations": collocations,
            "related_terms": related_terms, "confusables": confusables,
            "sources": [_dictionary(input_id)], "uncertainties": uncertainties,
        })
    return rows


def jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(
        (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        for row in rows
    )


def write_fixture(directory: Path) -> tuple[Path, Path]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    source_path = directory / "source.jsonl"
    output_path = directory / "enriched.jsonl"
    source_path.write_bytes(jsonl_bytes(INPUTS))
    output_path.write_bytes(jsonl_bytes(enriched_records()))
    return source_path, output_path
