"""Descriptive, paper-level phrase contrasts on visually reviewed learning abstracts."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
from stylelab import normalize, dump


def compare(records, manifest, splits, features, extracted_dir):
    """Validate every source before computing counts; never read held-out text."""
    by_id = {r['paper_id']: r for r in manifest}
    prepared = []
    seen = set()
    for r in records:
        pid = r['paper_id']
        if pid in seen:
            raise ValueError('One complete abstract per paper is required')
        seen.add(pid)
        if pid not in by_id or splits.get(pid) != 'learning' or by_id[pid].get('split') != 'learning':
            raise ValueError('Only registered learning papers are permitted')
        if r.get('role') not in {'target', 'reference'}:
            raise ValueError('Unknown contrast role')
        if r.get('section') != 'abstract' or r.get('reviewed') is not True or not r.get('reviewer'):
            raise ValueError('Visually reviewed abstracts with a reviewer are required')
        text = normalize(r.get('text', ''))
        if not text:
            raise ValueError('Empty abstract')
        page = r.get('page')
        if type(page) is not int or page < 1:
            raise ValueError('Invalid PDF page')
        prepared.append((r, text))
    if {r['role'] for r, _ in prepared} != {'target', 'reference'}:
        raise ValueError('Both groups are required')
    feature_ids = [f['id'] for f in features]
    if not features or len(set(feature_ids)) != len(features):
        raise ValueError('Feature IDs must be unique and nonempty')
    patterns = [(f, re.compile(f['pattern'], re.I)) for f in features]
    for r, text in prepared:
        source = json.loads((Path(extracted_dir) / (r['paper_id'] + '.json')).read_text(encoding='utf-8'))
        if source.get('paper_id') != r['paper_id'] or source.get('sha256') != by_id[r['paper_id']]['sha256']:
            raise ValueError('Source identity mismatch')
        pages = {p['page']: p['text'] for p in source['pages']}
        if r['page'] not in pages or text not in normalize(pages[r['page']]):
            raise ValueError('Abstract does not match the source page')
    results = []
    for f, pattern in patterns:
        hits = []
        for r, text in prepared:
            matches = list(pattern.finditer(text))
            if matches:
                hits.append({'paper_id': r['paper_id'], 'label': r['label'], 'role': r['role'],
                             'page': r['page'], 'quotes': [m.group(0) for m in matches]})
        results.append({'id': f['id'], 'description': f['description'], 'pattern': f['pattern'],
                        'counts': {role: {'hits': sum(h['role'] == role for h in hits),
                                         'papers': sum(r['role'] == role for r, _ in prepared)}
                                   for role in ['target', 'reference']}, 'evidence': hits})
    return {'status': 'exploratory_learning_sample_not_independent_validation',
            'unit': 'one_complete_abstract_per_paper',
            'limits': ['Patterns may have been selected after reading these samples.',
                       'Exact regex matches do not measure all paraphrases of a writing habit.',
                       'No significance test, authorship classifier, or imitation accuracy.',
                       'Journal, topic, date and coauthor confounding remain.'],
            'features': results}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--excerpts', type=Path, required=True)
    p.add_argument('--features', type=Path, default=Path('templates/contrast-features.json'))
    p.add_argument('--local', type=Path, default=Path('local'))
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if not a.out.resolve().is_relative_to(a.local.resolve()):
        p.error('Contrast evidence must be saved under the local data directory')
    read = lambda path: json.loads(path.read_text(encoding='utf-8'))
    result = compare([json.loads(s) for s in a.excerpts.read_text(encoding='utf-8').splitlines() if s.strip()],
                     read(a.local / 'manifest.json'), read(a.local / 'splits.json'),
                     read(a.features), a.local / 'extracted')
    dump(a.out, result)
    print(f'Validated {len(result["features"])} descriptive feature contrasts; not an efficacy score.')


if __name__ == '__main__':
    main()
