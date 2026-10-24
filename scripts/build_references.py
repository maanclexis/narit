#!/usr/bin/env python
"""Build (:Section)-[:REFERENCES]->(:Section) edges from Bare Act text.

Handles:
  - Explicit: 'section 34', 'Sec. 34', 's. 34', 'sections 99 to 106'
  - Relative: 'the last preceding section' -> N-1, 'the next following section' -> N+1

Skips:
  - Self-reference: 'in this section', 'of this section'
  - Cross-act: 'section 2 of the Information Technology Act'
  - Targets not in the graph

Usage:
  python scripts/build_references.py            # dry-run, show report
  python scripts/build_references.py --write    # create edges
  python scripts/build_references.py --sample 40
"""
import os
import re
import random
import argparse
from collections import Counter
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

RE_RANGE = re.compile(r'\bsections?\s+(\d{1,4})(?:\s+(?:to|-|through|and)\s+(\d{1,4}))', re.IGNORECASE)
RE_EXPLICIT = re.compile(r'\b(?:section|sections|sec\.|s\.)\s+(\d{1,4}[A-Z]?)(?![A-Za-z])', re.IGNORECASE)
RE_LAST_PRECEDING = re.compile(r'\b(?:the\s+)?last\s+preceding\s+section\b', re.IGNORECASE)
RE_NEXT_FOLLOWING = re.compile(r'\b(?:the\s+)?next\s+following\s+section\b', re.IGNORECASE)
RE_OTHER_ACT = re.compile(r'(?:of\s+the\s+([A-Z][A-Za-z\s]{2,60}?(?:Act|Code|Sanhita|Funds|Provisions))|of\s+(Act\s+\d+\s+of\s+\d{4})|of\s+(Bharatiya\s+(?:[A-Z][a-z]+\s+)+Sanhita)|of\s+(Indian\s+[A-Z][a-z]+\s+Code))', re.IGNORECASE)
RE_SELF_REF = re.compile(r'\b(?:in|of|under|this)\s+this\s+section\b', re.IGNORECASE)
RE_AMENDMENT = re.compile(r'(?:\(Amendment\)|Act[,\s]+\d{4}|Act\s+No\.\s*\d+|Act\s+\d+\s+of\s+\d{4}|State\s+Amendment|Vide\s+[A-Z][\w.\s]*Act)', re.IGNORECASE)


def fetch_all(session):
    rows = session.run('''
        MATCH (s:Section)
        RETURN s.uid AS uid, s.code AS code, s.number AS number,
               coalesce(s.text, '') AS text
    ''')
    return [r.data() for r in rows]


def is_self_reference(text, match_start):
    window_start = max(0, match_start - 40)
    window = text[window_start:match_start + 30]
    return bool(RE_SELF_REF.search(window))


def is_amendment_ref(text, match_start):
    window = text[max(0, match_start - 80):match_start]
    return bool(RE_AMENDMENT.search(window))


def is_cross_act(text, match_end, current_code):
    tail = text[match_end:match_end + 250]
    m = RE_OTHER_ACT.search(tail)
    if not m:
        return False
    act = next((g for g in m.groups() if g), '').lower()
    if not act:
        return False
    if current_code == 'IPC':
        return not ('indian penal code' in act or 'this code' in act)
    if current_code == 'BNS':
        return not ('bharatiya nyaya sanhita' in act or 'this sanhita' in act)
    return True


def is_any_external_act(text, match_start):
    window = text[max(0, match_start - 30):match_start]
    return bool(re.search(r'(?:of|under|vide)\s+(?:the\s+)?[A-Z]', window))


def extract_refs(section, valid_uids):
    uid = section['uid']
    code = section['code']
    number = str(section['number'])
    text = section['text']
    refs = []
    range_spans = []

    for m in RE_RANGE.finditer(text):
        range_spans.append((m.start(), m.end()))
        try:
            start = int(m.group(1))
            end = int(m.group(2))
        except (ValueError, TypeError):
            continue
        if start > end or (end - start) > 30:
            continue
        for n in range(start, end + 1):
            target = f'{code}_{n}'
            if target in valid_uids and target != uid:
                refs.append({
                    'target': target,
                    'pattern': 'range',
                    'raw': m.group(0),
                    'context': text[max(0, m.start() - 40):m.end() + 40].replace('\n', ' '),
                })

    for m in RE_EXPLICIT.finditer(text):
        if any(s <= m.start() <= e for s, e in range_spans):
            continue
        if is_self_reference(text, m.start()):
            continue
        if is_amendment_ref(text, m.start()):
            continue
        if is_cross_act(text, m.end(), code):
            continue
        target = f'{code}_{m.group(1)}'
        if target not in valid_uids or target == uid:
            continue
        refs.append({
            'target': target,
            'pattern': 'explicit',
            'raw': m.group(0),
            'context': text[max(0, m.start() - 40):m.end() + 40].replace('\n', ' '),
        })

    if number.isdigit():
        n = int(number)
        for m in RE_LAST_PRECEDING.finditer(text):
            target = f'{code}_{n - 1}'
            if n > 1 and target in valid_uids:
                refs.append({
                    'target': target,
                    'pattern': 'relative_prev',
                    'raw': m.group(0),
                    'context': text[max(0, m.start() - 40):m.end() + 40].replace('\n', ' '),
                })
        for m in RE_NEXT_FOLLOWING.finditer(text):
            target = f'{code}_{n + 1}'
            if target in valid_uids:
                refs.append({
                    'target': target,
                    'pattern': 'relative_next',
                    'raw': m.group(0),
                    'context': text[max(0, m.start() - 40):m.end() + 40].replace('\n', ' '),
                })

    seen = set()
    deduped = []
    for r in refs:
        if r['target'] not in seen:
            seen.add(r['target'])
            deduped.append(r)
    return deduped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true', help='actually create edges')
    ap.add_argument('--sample', type=int, default=20, help='sample size for spot-check')
    args = ap.parse_args()

    driver = GraphDatabase.driver(
        os.getenv('NEO4J_URI'),
        auth=(os.getenv('NEO4J_USER'), os.getenv('NEO4J_PASSWORD')),
    )

    with driver.session(database=os.getenv('NEO4J_DATABASE')) as s:
        sections = fetch_all(s)
        valid_uids = {x['uid'] for x in sections}
        print(f'Sections loaded: {len(sections)}')

        all_refs = []
        per_pattern = Counter()
        per_code = Counter()
        for sec in sections:
            refs = extract_refs(sec, valid_uids)
            for r in refs:
                r['source'] = sec['uid']
                all_refs.append(r)
                per_pattern[r['pattern']] += 1
                per_code[sec['code']] += 1

        print(f'Total REFERENCES found: {len(all_refs)}')
        print(f'By pattern: {dict(per_pattern)}')
        print(f'By source code: {dict(per_code)}')

        if not all_refs:
            print('Nothing to write.')
            driver.close()
            return

        sample = random.sample(all_refs, min(args.sample, len(all_refs)))
        print()
        print(f'=== SPOT-CHECK SAMPLE ({len(sample)}) ===')
        for r in sample:
            print(f"  {r['source']} -> {r['target']}  [{r['pattern']}]  raw='{r['raw']}'")
            print(f"    ctx: {r['context'][:120]}")

        if not args.write:
            print()
            print('DRY-RUN — no edges created. Run with --write to apply.')
            driver.close()
            return

        print()
        print('=== WRITING EDGES ===')
        written = 0
        cypher = '''
            MATCH (src:Section {uid: $src})
            MATCH (dst:Section {uid: $dst})
            MERGE (src)-[r:REFERENCES]->(dst)
            ON CREATE SET r.raw_text = $raw,
                          r.context = $ctx,
                          r.pattern_type = $pat
            RETURN r
        '''
        for r in all_refs:
            result = s.run(cypher, src=r['source'], dst=r['target'],
                           raw=r['raw'], ctx=r['context'], pat=r['pattern'])
            if result.single():
                written += 1
        print(f'Edges created/merged: {written}')

        verify = s.run('MATCH (:Section)-[r:REFERENCES]->(:Section) RETURN count(r) AS c').single()
        print(f'Total REFERENCES edges in graph: {verify["c"]}')

    driver.close()


if __name__ == '__main__':
    main()
