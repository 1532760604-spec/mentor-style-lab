import copy
import json
from pathlib import Path
import tempfile
import unittest
import re
from contrast import compare


class ContrastTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.records = []
        self.manifest = []
        for pid, role in [('p_a', 'target'), ('p_b', 'reference')]:
            text = 'Our findings suggest benefits. Our findings suggest costs.' if role == 'target' else 'No such phrase.'
            self.records.append(dict(paper_id=pid, role=role, label=pid, section='abstract',
                                     reviewed=True, reviewer='test_fixture', page=1, text=text))
            self.manifest.append(dict(paper_id=pid, sha256=pid, split='learning'))
            (self.root / (pid + '.json')).write_text(json.dumps(dict(paper_id=pid, sha256=pid,
                     pages=[dict(page=1, text=text)])), encoding='utf-8')
        self.splits = dict(p_a='learning', p_b='learning')
        self.features = [dict(id='F', description='test', pattern=r'Our findings suggest')]

    def run_compare(self):
        return compare(self.records, self.manifest, self.splits, self.features, self.root)

    def test_repeated_phrase_counts_as_one_paper(self):
        f = self.run_compare()['features'][0]
        self.assertEqual(f['counts']['target'], {'hits': 1, 'papers': 1})
        self.assertEqual(len(f['evidence'][0]['quotes']), 2)
        self.assertEqual(f['counts']['reference']['hits'], 0)

    def test_heldout_rejected_before_any_source_read(self):
        self.splits['p_b'] = 'test'
        for path in self.root.iterdir():
            path.unlink()
        with self.assertRaisesRegex(ValueError, 'learning'):
            self.run_compare()

    def test_mislabeled_manifest_rejected(self):
        self.manifest[0]['split'] = 'development'
        with self.assertRaisesRegex(ValueError, 'learning'):
            self.run_compare()

    def test_duplicate_paper_cannot_inflate_sample(self):
        self.records.append(copy.deepcopy(self.records[0]))
        with self.assertRaisesRegex(ValueError, 'One complete'):
            self.run_compare()

    def test_fabricated_or_wrong_page_quote_rejected(self):
        self.records[0]['text'] = 'Invented evidence.'
        with self.assertRaisesRegex(ValueError, 'source page'):
            self.run_compare()

    def test_unreviewed_or_unlabeled_evidence_rejected(self):
        self.records[0]['reviewed'] = False
        with self.assertRaisesRegex(ValueError, 'reviewed'):
            self.run_compare()

    def test_method_label_does_not_match_plain_the_results(self):
        config = json.loads((Path(__file__).resolve().parents[1] / 'templates/contrast-features.json').read_text(encoding='utf-8'))
        f = next(f for f in config if f['id'] == 'F08')
        pattern = re.compile(f['pattern'], re.I)
        self.assertIsNone(pattern.search('The results show a difference.'))
        self.assertIsNotNone(pattern.search('The ETR results show a difference.'))
        self.assertIsNotNone(pattern.search('The results of the FR model show a difference.'))


if __name__ == '__main__':
    unittest.main()
