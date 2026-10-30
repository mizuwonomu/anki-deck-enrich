from __future__ import annotations

import copy
import html
import unittest
from dataclasses import replace
from html.parser import HTMLParser
from pathlib import Path

from jp_deck.audit import AuditError, audit_rendered_record, visible_text
from jp_deck.render import render_preview, render_record
from jp_deck.validation import read_jsonl

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests/fixtures/synthetic/enriched.jsonl"
EXPECTED_FRONT = [
    ("試作重複語", "試作重複語を試す"),
    ("霧環", "霧環を試す"),
    ("星綴", "星綴を試す"),
    ("試作重複語", "試作重複語を試す"),
    ("波標", "波標を試す"),
]


class AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.anchors = []

    def handle_starttag(self, tag, attrs):
        self.anchors.append((tag, dict(attrs)))


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.records = read_jsonl(DATA, "fabricated synthetic render inputs")

    def test_exact_front_pairs_and_ordered_fields(self):
        for record, (word, collocation) in zip(self.records, EXPECTED_FRONT, strict=True):
            with self.subTest(input_id=record["input_id"]):
                rendered = render_record(record)
                self.assertEqual((rendered.expression, rendered.front_collocation), (word, collocation))
                self.assertEqual(rendered.anki_fields[:2], [word, collocation])
                self.assertNotIn(record["headword"]["reading"], rendered.anki_fields[0])

    def test_all_content_and_scope_audit_passes(self):
        for record in self.records:
            with self.subTest(input_id=record["input_id"]):
                report = audit_rendered_record(record, render_record(record))
                self.assertTrue(report["source_links_scope_checked"])
                self.assertEqual(report["internal_metadata_leak_check"], "passed")

    def test_audit_rejects_explanation_swapped_between_sense_sections(self):
        record = self.records[0]
        rendered = render_record(record)
        expected = {
            "sense-001-one": (
                "Nghĩa giả lập A của mục 1.",
                "Giải thích kiểm thử A dành riêng cho mục 1.",
            ),
            "sense-001-two": (
                "Nghĩa giả lập B của mục 1.",
                "Giải thích kiểm thử B dành riêng cho mục 1.",
            ),
        }
        for sense_id, (meaning, explanation) in expected.items():
            section_text = visible_text(rendered.sense_sections[sense_id])
            self.assertIn(meaning, section_text)
            self.assertIn(explanation, section_text)
            other_explanation = expected[next(key for key in expected if key != sense_id)][1]
            self.assertNotIn(other_explanation, section_text)

        first_explanation = html.escape(expected["sense-001-one"][1], quote=True)
        second_explanation = html.escape(expected["sense-001-two"][1], quote=True)

        def swap_explanation(markup):
            marker = "__TEST_EXPLANATION_SWAP__"
            return (markup.replace(first_explanation, marker)
                    .replace(second_explanation, first_explanation)
                    .replace(marker, second_explanation))

        corrupted = replace(
            rendered,
            back_html=swap_explanation(rendered.back_html),
            sense_sections={key: swap_explanation(value) for key, value in rendered.sense_sections.items()},
        )
        with self.assertRaisesRegex(
            AuditError,
            r"record demo-001 path /senses/sense-001-one/explanation_vi",
        ):
            audit_rendered_record(record, corrupted)

    def test_evidence_link_is_bound_to_claim_pointer_not_just_item(self):
        record = copy.deepcopy(self.records[0])
        rendered = render_record(record)
        record["examples"][0]["evidence_refs"][0]["claim_path"] = "/examples/0/translation_vi"
        with self.assertRaisesRegex(AuditError, r"/examples/0/translation_vi: evidence link is not attached to its exact claim"):
            audit_rendered_record(record, rendered)

    def test_example_sentence_reading_and_translation_stay_paired(self):
        record = self.records[0]
        rendered = render_record(record)
        first, second = (item["translation_vi"] for item in record["examples"])
        swapped_html = rendered.back_html.replace(first, "__SWAP_FIRST__").replace(second, first).replace("__SWAP_FIRST__", second)
        corrupted = replace(rendered, back_html=swapped_html)
        with self.assertRaisesRegex(RuntimeError, r"record demo-001 path /examples: learning text or source links are paired"):
            audit_rendered_record(record, corrupted)

    def test_examples_and_collocations_are_grouped_under_their_sense(self):
        record = self.records[0]
        rendered = render_record(record)
        first_sense = visible_text(rendered.sense_sections["sense-001-one"])
        second_sense = visible_text(rendered.sense_sections["sense-001-two"])
        for example in record["examples"]:
            self.assertIn(example["sentence_ja"], second_sense)
            self.assertNotIn(example["sentence_ja"], first_sense)
        for collocation in record["collocations"]:
            self.assertIn(collocation["expression"], second_sense)
            self.assertNotIn(collocation["expression"], first_sense)

    def test_html_dynamic_text_is_escaped_and_not_interpreted(self):
        record = copy.deepcopy(self.records[0])
        record["senses"][0]["explanation_vi"] = 'literal <script>alert("x")</script> & more'
        rendered = render_record(record)
        self.assertNotIn("<script>", rendered.back_html)
        self.assertIn("&lt;script&gt;", rendered.back_html)
        self.assertIn("&amp; more", rendered.back_html)
        record["headword"]["expression"] = '<img src=x onerror="alert(1)">'
        front = render_record(record)
        self.assertEqual(html.unescape(front.anki_fields[0]), record["headword"]["expression"])
        self.assertNotIn('<img src=x onerror="alert(1)">', front.anki_fields[0])

    def test_http_source_url_attribute_is_escaped(self):
        record = copy.deepcopy(self.records[0])
        url = 'https://example.test/entry?q=1&x=%22%20onmouseover%3Dalert(1)'
        record["sources"][0]["url"] = url
        rendered = render_record(record)
        self.assertIn("&amp;", rendered.back_html)
        parser = AnchorParser()
        parser.feed(rendered.back_html)
        links = [attrs["href"] for tag, attrs in parser.anchors if tag == "a"]
        self.assertIn(url, links)
        self.assertFalse(any("onmouseover" in attrs for _, attrs in parser.anchors))

    def test_unsafe_source_scheme_is_rejected(self):
        record = copy.deepcopy(self.records[0])
        record["sources"][0]["url"] = "javascript:alert(1)"
        with self.assertRaisesRegex(ValueError, r"only absolute HTTP\(S\)"):
            render_record(record)

    def test_missing_first_collocation_fails_actionably(self):
        record = copy.deepcopy(self.records[0])
        record["collocations"] = []
        with self.assertRaisesRegex(ValueError, r"record demo-001 path /collocations/0/expression"):
            render_record(record)

    def test_null_frequency_is_not_rendered_as_zero(self):
        rendered = render_record(self.records[0])
        self.assertIn("Tần suất corpus: chưa có số đo.", rendered.back_html)
        self.assertNotIn("Tần suất corpus: 0", rendered.back_html)

    def test_preview_has_only_learner_content_without_debug_or_uncertainty_text(self):
        rendered = [render_record(record) for record in self.records]
        preview = render_preview(rendered)
        self.assertEqual(preview.count('class="preview-card"'), 5)
        self.assertNotIn("demo-001", preview)
        self.assertNotIn("sense-001-two", preview)
        self.assertNotIn("claim_path", preview)
        displayed_fields = visible_text("\n".join(field for item in rendered for field in item.anki_fields))
        displayed_preview = visible_text(preview)
        for record in self.records:
            for uncertainty in record["uncertainties"]:
                with self.subTest(input_id=record["input_id"]):
                    self.assertNotIn(uncertainty["issue_vi"], displayed_fields, "diagnostic issue text is visible in note fields")
                    self.assertNotIn(uncertainty["issue_vi"], displayed_preview, "diagnostic issue text is visible in preview.html")
        self.assertNotIn('class="uncertainties"', "\n".join(item.back_html for item in rendered))


if __name__ == "__main__":
    unittest.main()
