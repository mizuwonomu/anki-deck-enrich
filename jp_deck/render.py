"""Escaped, sense-aware learner HTML and standalone card preview."""

from __future__ import annotations

import html
from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import urlsplit
from typing import Any


@dataclass(frozen=True)
class RenderedRecord:
    expression: str
    front_collocation: str
    back_html: str
    headword_html: str
    sense_sections: dict[str, str]
    citation_urls: tuple[str, ...]

    @property
    def anki_fields(self) -> list[str]:
        # These exact three fields are in the same order as Model.fields.
        return [html.escape(self.expression, quote=True), html.escape(self.front_collocation, quote=True), self.back_html]


def _text(value: str) -> str:
    return html.escape(value, quote=True)


def _safe_http_url(url: str, *, context: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{context}: only absolute HTTP(S) source URLs may be linked")
    return url


def _source_label(source: dict[str, Any]) -> str:
    provider_labels = {"jmdict": "JMdict", "tatoeba": "Tatoeba", "weblio": "Weblio", "twc": "TWC"}
    return source["attribution"] or source["underlying_source"] or provider_labels[source["provider"]]


def _citations(
    source_ids: list[str],
    sources: dict[str, dict[str, Any]],
    *,
    label: str = "Nguồn",
) -> tuple[str, tuple[str, ...]]:
    if not source_ids:
        return "", ()
    fragments: list[str] = []
    urls: list[str] = []
    seen: set[str] = set()
    for source_id in source_ids:
        if source_id in seen:
            continue
        seen.add(source_id)
        source = sources[source_id]
        url = _safe_http_url(source["url"], context=f"source {source_id}")
        urls.append(url)
        citation = f'<a href="{_text(url)}" target="_blank" rel="noopener noreferrer">{_text(_source_label(source))}</a>'
        if source["license"] is not None:
            citation += f' <span class="license">({_text(source["license"])})</span>'
        fragments.append(citation)
    return f'<p class="source-line"><span>{_text(label)}:</span> {"; ".join(fragments)}</p>', tuple(urls)


def _evidence_ids(item: dict[str, Any]) -> list[str]:
    return [ref["source_id"] for ref in item.get("evidence_refs", [])]


def _origin_label(origin: str) -> str:
    return {"quoted": "Trích dẫn", "adapted": "Phỏng theo", "generated": "Tự biên soạn"}[origin]


def _relationship_label(relationship: str) -> str:
    return {"synonym": "Đồng nghĩa", "near_synonym": "Gần nghĩa", "related": "Có liên quan"}[relationship]


def render_record(record: dict[str, Any]) -> RenderedRecord:
    record_id = record["input_id"]
    if not record["collocations"]:
        raise ValueError(f"record {record_id} path /collocations/0/expression: front requires an existing collocation")
    sources = {source["source_id"]: source for source in record["sources"]}
    citation_urls: list[str] = []
    claim_sources: dict[str, list[str]] = defaultdict(list)

    def collect_claim_refs(value: Any) -> None:
        if isinstance(value, dict):
            for ref in value.get("evidence_refs", []):
                claim_sources[ref["claim_path"]].append(ref["source_id"])
            for key, item in value.items():
                if key != "evidence_refs":
                    collect_claim_refs(item)
        elif isinstance(value, list):
            for item in value:
                collect_claim_refs(item)

    collect_claim_refs(record)

    def cited_field(path: str, markup: str) -> tuple[str, tuple[str, ...]]:
        citation, urls = _citations(claim_sources.get(path, []), sources, label="Nguồn hỗ trợ")
        if not citation:
            return markup, ()
        return f'<div class="claim">{markup}{citation}</div>', urls

    expression = record["headword"]["expression"]
    front_collocation = record["collocations"][0]["expression"]
    headword_claim, urls = cited_field(
        "/headword/expression", f'<h2 class="word">{_text(expression)}</h2>'
    )
    parts = [
        '<section class="headword">',
        headword_claim,
        f'<p class="reading">{_text(record["headword"]["reading"])}</p>',
        f'<p class="pos">Từ loại: {_text("; ".join(record["headword"]["pos"]))}</p>',
    ]
    citation_urls.extend(urls)
    parts.append("</section>")
    headword_html = "".join(parts)

    groups: dict[str, list[tuple[str, dict[str, Any]]]] = {
        sense["sense_id"]: [] for sense in record["senses"]
    }
    item_indexes = {
        id(item): index
        for collection in ("examples", "collocations", "related_terms", "confusables")
        for index, item in enumerate(record[collection])
    }
    for collection, kind in (
        ("examples", "example"),
        ("collocations", "collocation"),
        ("related_terms", "related"),
        ("confusables", "confusable"),
    ):
        for item in record[collection]:
            groups[item["sense_id"]].append((kind, item))

    sense_sections: dict[str, str] = {}
    for sense_index, sense in enumerate(record["senses"], start=1):
        sense_id = sense["sense_id"]
        sense_claim, urls = cited_field(
            f"/senses/{sense_index - 1}/meaning_vi",
            f'<h3>Nghĩa {sense_index}: {_text(sense["meaning_vi"])}</h3>',
        )
        section = [
            '<section class="sense">',
            sense_claim,
            f'<p class="explanation">{_text(sense["explanation_vi"])}</p>',
        ]
        citation_urls.extend(urls)

        examples = [item for kind, item in groups[sense_id] if kind == "example"]
        if examples:
            section.append('<section class="subsection examples"><h4>Ví dụ</h4>')
            for item in examples:
                example_index = item_indexes[id(item)]
                sentence_claim, urls = cited_field(
                    f"/examples/{example_index}/sentence_ja",
                    f'<p class="japanese">{_text(item["sentence_ja"])}</p>',
                )
                section.extend(
                    [
                        '<article class="learning-item example">',
                        sentence_claim,
                        f'<p class="reading">{_text(item["reading"])}</p>',
                        f'<p class="translation">{_text(item["translation_vi"])}</p>',
                        f'<p class="origin">Nguồn gốc: {_text(_origin_label(item["origin"]))}</p>',
                    ]
                )
                citation_urls.extend(urls)
                html_chunk, urls = _citations(item["origin_source_ids"], sources, label="Nguồn gốc")
                section.append(html_chunk)
                citation_urls.extend(urls)
                section.append("</article>")
            section.append("</section>")

        collocations = [item for kind, item in groups[sense_id] if kind == "collocation"]
        if collocations:
            section.append('<section class="subsection collocations"><h4>Kết hợp từ</h4>')
            for item in collocations:
                item_index = item_indexes[id(item)]
                expression_claim, urls = cited_field(
                    f"/collocations/{item_index}/expression",
                    f'<p class="japanese">{_text(item["expression"])}</p>',
                )
                section.extend(
                    [
                        '<article class="learning-item collocation">',
                        expression_claim,
                        f'<p class="reading">{_text(item["reading"])}</p>',
                        f'<p class="meaning">{_text(item["meaning_vi"])}</p>',
                        f'<p class="usage">{_text(item["usage_vi"])}</p>',
                        '<p class="frequency">Tần suất corpus: chưa có số đo.</p>'
                        if item["frequency"] is None
                        else (
                            '<p class="frequency">Tần suất corpus: '
                            f'{item["frequency"]["count"]} ({_text(item["frequency"]["corpus"])}, '
                            f'{_text(item["frequency"]["query"])}).</p>'
                        ),
                    ]
                )
                citation_urls.extend(urls)
                section.append("</article>")
            section.append("</section>")

        related_terms = [item for kind, item in groups[sense_id] if kind == "related"]
        if related_terms:
            section.append('<section class="subsection related"><h4>Từ liên quan</h4>')
            for item in related_terms:
                item_index = item_indexes[id(item)]
                claims: list[str] = []
                for field, class_name, value in (
                    ("expression", "japanese", item["expression"]),
                    ("reading", "reading", item["reading"]),
                    ("relationship", "relationship", _relationship_label(item["relationship"])),
                    ("note_vi", "note", item["note_vi"]),
                ):
                    claim_html, urls = cited_field(
                        f"/related_terms/{item_index}/{field}",
                        f'<p class="{class_name}">{_text(value)}</p>',
                    )
                    claims.append(claim_html)
                    citation_urls.extend(urls)
                section.append('<article class="learning-item related-term">')
                section.extend(claims)
                section.append("</article>")
            section.append("</section>")

        confusables = [item for kind, item in groups[sense_id] if kind == "confusable"]
        if confusables:
            section.append('<section class="subsection confusables"><h4>Từ dễ nhầm</h4>')
            for item in confusables:
                item_index = item_indexes[id(item)]
                section.append('<article class="learning-item confusable">')
                for field, class_name, value in (
                    ("expression", "japanese", item["expression"]),
                    ("reading", "reading", item["reading"]),
                    ("distinction_vi", "distinction", item["distinction_vi"]),
                ):
                    claim_html, urls = cited_field(
                        f"/confusables/{item_index}/{field}",
                        f'<p class="{class_name}">{_text(value)}</p>',
                    )
                    section.append(claim_html)
                    citation_urls.extend(urls)
                for contrast_index, contrast in enumerate(item["contrast_examples"]):
                    sentence_claim, urls = cited_field(
                        f"/confusables/{item_index}/contrast_examples/{contrast_index}/sentence_ja",
                        f'<p class="japanese">{_text(contrast["sentence_ja"])}</p>',
                    )
                    reading_claim, reading_urls = cited_field(
                        f"/confusables/{item_index}/contrast_examples/{contrast_index}/reading",
                        f'<p class="reading">{_text(contrast["reading"])}</p>',
                    )
                    translation_claim, translation_urls = cited_field(
                        f"/confusables/{item_index}/contrast_examples/{contrast_index}/translation_vi",
                        f'<p class="translation">{_text(contrast["translation_vi"])}</p>',
                    )
                    section.extend(
                        [
                            '<div class="contrast-example">',
                            sentence_claim,
                            reading_claim,
                            translation_claim,
                            f'<p class="origin">Nguồn gốc: {_text(_origin_label(contrast["origin"]))}</p>',
                        ]
                    )
                    citation_urls.extend(urls)
                    citation_urls.extend(reading_urls)
                    citation_urls.extend(translation_urls)
                    html_chunk, urls = _citations(contrast["origin_source_ids"], sources, label="Nguồn gốc")
                    section.append(html_chunk)
                    citation_urls.extend(urls)
                    section.append("</div>")
                section.append("</article>")
            section.append("</section>")

        section.append("</section>")
        section_html = "".join(section)
        sense_sections[sense_id] = section_html
        parts.append(section_html)

    return RenderedRecord(
        expression=expression,
        front_collocation=front_collocation,
        back_html="".join(parts),
        headword_html=headword_html,
        sense_sections=sense_sections,
        citation_urls=tuple(citation_urls),
    )


CSS = """\
.card { font-family: -apple-system, BlinkMacSystemFont, "Noto Sans", "Noto Sans CJK JP", sans-serif;
        color: #20252b; background: #fff; font-size: 18px; line-height: 1.65; text-align: left;
        max-width: 780px; margin: 0 auto; padding: 1.15rem; overflow-wrap: anywhere; }
.front { text-align: center; padding: 1.8rem .5rem; }
.front-expression { font-size: 2.15rem; font-weight: 700; }
.front-collocation { margin-top: .85rem; font-size: 1.35rem; }
.word { margin: 0; font-size: 1.8rem; }
.reading { color: #526477; margin: .2rem 0; }
.pos { color: #526477; }
.sense { border-top: 1px solid #dce2e8; margin-top: 1.25rem; padding-top: .65rem; }
.sense h3 { font-size: 1.25rem; margin: .3rem 0; }
.subsection { margin: .8rem 0; }
.subsection h4 { font-size: 1rem; margin: .5rem 0; color: #394d61; }
.learning-item { border-left: 3px solid #cbd8e5; margin: .55rem 0; padding: .2rem .8rem; }
.learning-item p, .contrast-example p { margin: .2rem 0; }
.japanese { font-size: 1.1rem; }
.translation, .meaning, .note, .explanation, .usage { white-space: pre-wrap; }
.source-line { font-size: .8rem; color: #596a79; margin: .25rem 0 .5rem; }
.source-line a { color: #245d8f; }
.license { color: #697989; }
"""


def render_preview(rendered: list[RenderedRecord]) -> str:
    cards: list[str] = []
    for item in rendered:
        cards.append(
            '<article class="preview-card">'
            '<div class="card front">'
            f'<div class="front-expression">{_text(item.expression)}</div>'
            f'<div class="front-collocation">{_text(item.front_collocation)}</div>'
            '</div><hr><div class="card back">'
            f'{item.back_html}'
            '</div></article>'
        )
    return (
        '<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>JP Vocabulary MVP M1 — Anki preview</title>'
        f'<style>{CSS}body{{margin:0;padding:1rem;background:#f0f2f5}}'
        '.preview-card{background:white;border:1px solid #d5dbe2;border-radius:10px;'
        'margin:1rem auto;max-width:860px;box-shadow:0 2px 7px #0001}.preview-card hr{'
        'border:0;border-top:1px dashed #c5cdd5;margin:.2rem 1rem}</style></head><body>'
        + "".join(cards)
        + '</body></html>'
    )
