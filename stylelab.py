"""Read-only PDF intake and auditable, manually curated style evidence."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
import statistics
import unicodedata

ROOT = Path(__file__).resolve().parent


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize(text):
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"(?<=[a-zA-Z])\u00ad\s*\n\s*(?=[a-zA-Z])", "", text).replace("\u00ad", "")
    text = re.sub(r"(?<=[a-zA-Z])-\s*\n\s*(?=[a-zA-Z])", "", text)
    return " ".join(text.split())


def title_key(path):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKC", Path(path).stem).lower())


def version_groups(records):
    """Conservative filename-only candidate grouping; requires human review."""
    parent = {r["paper_id"]: r["paper_id"] for r in records}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    pairs = []
    for i, a in enumerate(records):
        for b in records[i + 1:]:
            ka, kb = title_key(a["sources"][0]), title_key(b["sources"][0])
            score = SequenceMatcher(None, ka, kb).ratio() if ka and kb else 0
            if min(len(ka), len(kb)) >= 30 and score >= .92:
                ra, rb = find(a["paper_id"]), find(b["paper_id"])
                parent[max(ra, rb)] = min(ra, rb)
                pairs.append({"a": a["paper_id"], "b": b["paper_id"],
                              "filename_similarity": round(score, 3), "reviewed": False})
    groups = defaultdict(list)
    for r in records:
        groups[find(r["paper_id"])].append(r["paper_id"])
    return list(groups.values()), pairs


def assign_splits(groups, previous):
    output = dict(previous)
    allowed = {"learning", "development", "test"}
    if set(previous.values()) - allowed:
        raise ValueError("Unknown split in persisted assignments")
    for ids in groups:
        old = {previous[i] for i in ids if i in previous}
        if len(old) > 1:
            raise ValueError(f"Version group crosses frozen splits: {ids}. Review explicitly.")
        number = int(hashlib.sha256(min(ids).encode()).hexdigest()[:8], 16) % 10
        split = next(iter(old)) if old else ("test" if number == 0 else
                                            "development" if number == 1 else "learning")
        for i in ids:
            output[i] = split
    return output


def ingest(source, local):
    import pymupdf
    source = source.resolve()
    if not source.is_dir():
        raise ValueError(f"Source directory not found: {source}")
    files = sorted(p for p in source.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")
    if not files:
        raise ValueError("No PDF files found")
    by_hash = {}
    for path in files:
        sha = digest(path)
        if sha in by_hash:
            by_hash[sha]["sources"].append(str(path))
            continue
        paper_id = "p_" + sha
        record = {"paper_id": paper_id, "sha256": sha, "sources": [str(path)],
                  "filename": path.name, "folder_year": path.parent.name,
                  "status": "needs_visual_review", "authorship": "unconfirmed_coauthored"}
        try:
            with pymupdf.open(path) as doc:
                if doc.needs_pass:
                    raise ValueError("Password-protected PDF")
                pages = []
                for n, page in enumerate(doc, 1):
                    # PDF internal order is retained. Never claim two-column reading order is verified.
                    text = page.get_text("text", sort=False)
                    blocks = [{"bbox": list(b[:4]), "text": b[4]} for b in
                              page.get_text("blocks", sort=False) if b[6] == 0]
                    pages.append({"page": n, "text": text, "blocks": blocks,
                                  "needs_ocr_or_review": len(text.strip()) < 100})
                record["pages"] = len(pages)
                record["characters"] = sum(len(p["text"]) for p in pages)
                record["low_text_pages"] = [p["page"] for p in pages if p["needs_ocr_or_review"]]
                record["metadata_title"] = doc.metadata.get("title", "")
                record["metadata_author"] = doc.metadata.get("author", "")
                record["extractor"] = "PyMuPDF " + pymupdf.__version__
                dump(local / "extracted" / (paper_id + ".json"),
                     {"paper_id": paper_id, "sha256": sha, "reading_order_verified": False, "pages": pages})
        except Exception as exc:
            record["status"] = "extraction_failed"
            record["error"] = str(exc)
        by_hash[sha] = record
    records = list(by_hash.values())
    groups, pairs = version_groups(records)
    split_path = local / "splits.json"
    previous = json.loads(split_path.read_text(encoding="utf-8")) if split_path.exists() else {}
    splits = assign_splits(groups, previous)
    for r in records:
        r["split"] = splits[r["paper_id"]]
    dump(split_path, splits)
    dump(local / "manifest.json", records)
    dump(local / "reports" / "version-candidates.json", pairs)
    counts = Counter(r["split"] for r in records)
    errors = [r for r in records if r["status"] == "extraction_failed"]
    low = [r for r in records if r.get("low_text_pages")]
    summary = {"pdf_files": len(files), "unique_files": len(records),
               "exact_duplicate_copies": len(files) - len(records),
               "version_candidate_pairs": len(pairs), "candidate_groups": len(groups),
               "pages": sum(r.get("pages", 0) for r in records),
               "extraction_failures": len(errors), "documents_with_low_text_pages": len(low),
               "splits": dict(counts), "reviewed_documents": 0}
    dump(local / "reports" / "summary.json", summary)
    lines = ["# 本地语料登记", "", "自动提取未等于可学习语料。所有 PDF 仍需确认阅读顺序、文章类型与作者贡献。", "",
             "```json", json.dumps(summary, ensure_ascii=False, indent=2), "```", "",
             "疑似版本按文件名保守聚组，避免明显同文版本跨集合；无法识别标题完全不同的版本。需人工审核后冻结。", "",
             "| ID（缩写） | 集合 | PDF页数 | 低文字页数 | 文件名 |", "|---|---|---:|---:|---|"]
    for r in records:
        lines.append(f"| {r['paper_id'][:14]} | {r['split']} | {r.get('pages', 0)} | "
                     f"{len(r.get('low_text_pages', []))} | {r['filename'].replace('|', ' ')} |")
    (local / "reports" / "inventory.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def validate_excerpts(rows, local):
    records = {r["paper_id"]: r for r in json.loads((local / "manifest.json").read_text(encoding="utf-8"))}
    splits = json.loads((local / "splits.json").read_text(encoding="utf-8"))
    seen = set()
    for r in rows:
        paper_id = r["paper_id"]
        if paper_id not in records or splits.get(paper_id) != "learning":
            raise ValueError("Only registered learning papers may enter style profiles")
        if r.get("reviewed") is not True or not r.get("authorship") or not r.get("section"):
            raise ValueError("Reviewed status, section and authorship are required")
        text = normalize(r["text"])
        if len(re.findall(r"\b[A-Za-z]+\b", text)) < 30:
            raise ValueError("Use a full prose passage with at least 30 English words")
        if text in seen:
            raise ValueError("Duplicate excerpt")
        seen.add(text)
        data = json.loads((local / "extracted" / (paper_id + ".json")).read_text(encoding="utf-8"))
        page_number = r["page"]
        if type(page_number) is not int or not 1 <= page_number <= len(data["pages"]):
            raise ValueError("Invalid PDF page number")
        if text not in normalize(data["pages"][page_number - 1]["text"]):
            raise ValueError("Excerpt is not verbatim text on its stated PDF page")
    if not rows:
        raise ValueError("No reviewed excerpts")


def surface_stats(rows):
    lengths, tokens = [], []
    for row in rows:
        text = normalize(row["text"])
        tokens.extend(re.findall(r"\b[A-Za-z]+(?:'[A-Za-z]+)?\b", text.lower()))
        lengths.extend(len(re.findall(r"\b[A-Za-z]+\b", s)) for s in re.split(r"(?<=[.!?])\s+", text) if s.strip())
    frequencies = Counter(tokens)
    vocab = ["however", "therefore", "thus", "moreover", "suggest", "suggests", "may", "might", "we"]
    return {"papers": len({r["paper_id"] for r in rows}), "passages": len(rows), "words": len(tokens),
            "approx_sentence_length_mean": round(statistics.mean(lengths), 2),
            "markers_per_1000_words": {w: round(frequencies[w] * 1000 / len(tokens), 2) for w in vocab}}


def profile(excerpts, local):
    rows = [json.loads(line) for line in excerpts.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    validate_excerpts(rows, local)
    sections = defaultdict(list)
    for r in rows:
        sections[r["section"]].append(r)
    result = {"status": "descriptive_not_validated_author_style", "overall": surface_stats(rows),
              "sections": {s: surface_stats(rs) for s, rs in sections.items()},
              "provenance": [{k: r[k] for k in ("paper_id", "page", "section", "authorship")} for r in rows],
              "limitations": "Regex sentence boundaries are approximate. Counts do not measure style accuracy or personal authorship."}
    dump(local / "profiles" / "surface-style.json", result)
    print(json.dumps(result["overall"], indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", type=Path, default=ROOT / "local")
    commands = parser.add_subparsers(dest="command", required=True)
    intake = commands.add_parser("ingest")
    intake.add_argument("--source", type=Path, required=True)
    stats = commands.add_parser("profile")
    stats.add_argument("--excerpts", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "ingest":
            ingest(args.source, args.local)
        else:
            profile(args.excerpts, args.local)
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
