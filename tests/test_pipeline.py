import json
from pathlib import Path
import tempfile
import unittest

import pymupdf
from stylelab import (assign_splits, digest, dump, ingest, normalize, select_papers,
                      validate_excerpts, validate_selection, verify_sheet, version_groups)

TEXT = ("We examine the relationship between service access and household outcomes. "
        "The analysis uses an illustrative sample for a software test only. "
        "These findings suggest a possible association, although the design does not establish a causal effect.")


class PipelineTests(unittest.TestCase):
    def test_reference_author_is_not_target_evidence(self):
        with self.assertRaises(ValueError):
            validate_selection([{"paper_id": "other-author"}],
                               [{"paper_id": "other-author", "role": "field_reference"}])

    def test_quote_provenance_and_independent_paper_count(self):
        rows = [{"excerpt_id": "e1", "paper_id": "p1", "text": TEXT}]
        rule = {"id": "r1", "support_papers": 1, "status": "tentative",
                "evidence": [{"excerpt_id": "e1", "quote": "possible association"}]}
        self.assertEqual(verify_sheet({"rules": [rule]}, rows)[0]["independent_papers"], 1)
        with self.assertRaises(ValueError):
            verify_sheet({"rules": [dict(rule, support_papers=3)]}, rows)
        with self.assertRaises(ValueError):
            verify_sheet({"rules": [dict(rule, status="cross_paper_observation")]}, rows)
        with self.assertRaises(ValueError):
            verify_sheet({"rules": [dict(rule, evidence=[{"excerpt_id": "e1", "quote": "certain effect"}])]}, rows)

    def test_soft_line_end_hyphen(self):
        self.assertEqual(normalize("agricul\u00ad\ntural"), "agricultural")

    def test_split_conflict_is_rejected(self):
        with self.assertRaises(ValueError):
            assign_splits([["a", "b"]], {"a": "learning", "b": "test"})

    def test_new_version_inherits_old_split(self):
        self.assertEqual(assign_splits([["a", "b"]], {"b": "test"})["a"], "test")

    def test_similar_versions_are_grouped(self):
        rows = [{"paper_id": "a", "sources": ["Household welfare and agricultural service access.pdf"]},
                {"paper_id": "b", "sources": ["Household welfare and agricultural service access (1).pdf"]}]
        groups, pairs = version_groups(rows)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(pairs), 1)

    def test_intake_and_evidence_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source, local = base / "source", base / "local"
            source.mkdir()
            path = source / "Synthetic study for pipeline validation.pdf"
            doc = pymupdf.open()
            page = doc.new_page()
            page.insert_textbox((50, 50, 550, 750), TEXT)
            doc.save(path)
            doc.close()
            (source / "copy.pdf").write_bytes(path.read_bytes())
            sha = digest(path)
            ingest(source, local)
            self.assertEqual(digest(path), sha)
            manifest = json.loads((local / "manifest.json").read_text())
            self.assertEqual(len(manifest), 1)
            self.assertEqual(len(manifest[0]["sources"]), 2)
            split_before = (local / "splits.json").read_bytes()
            selected_path = local / "selected.json"
            select_papers(source, local, selected_path)
            self.assertEqual(len(json.loads(selected_path.read_text())), 1)
            self.assertEqual(split_before, (local / "splits.json").read_bytes())
            with self.assertRaises(ValueError):
                select_papers(source, local, selected_path)
            pid = manifest[0]["paper_id"]
            row = {"paper_id": pid, "page": 1, "section": "results", "text": TEXT,
                   "reviewed": True, "authorship": "synthetic_fixture"}
            dump(local / "splits.json", {pid: "test"})
            with self.assertRaises(ValueError):
                validate_excerpts([row], local)
            dump(local / "splits.json", {pid: "learning"})
            validate_excerpts([row], local)
            with self.assertRaises(ValueError):
                validate_excerpts([dict(row, reviewed=False)], local)
            with self.assertRaises(ValueError):
                validate_excerpts([dict(row, text=TEXT.replace("possible", "certain"))], local)
            with self.assertRaises(ValueError):
                validate_excerpts([row, row], local)


if __name__ == "__main__":
    unittest.main()
