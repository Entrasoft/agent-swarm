"""Target selection rule for coordination v0.3, without network access."""

import unittest

from swarm_lab import v03_targets

TABLE = b'''<TABLE>
<TD><A title="n=20, k=8" class="tab" HREF="x">7</A></TD>
<TD><A title="n=22, k=8" class="tab" HREF="x">9-10</A></TD>
<TD><A title="n=40, k=8" class="tab" HREF="x">17-18</A></TD>
<TD><A title="n=50, k=14" class="tab" HREF="x">20-22</A></TD>
<TD><A title="n=40, k=15" class="tab" HREF="x">12-13</A></TD>
</TABLE>'''


def entry_page(lower, upper, modified, construction='Shortening of [1] at { 25 }'):
    return (f'<H3>Bounds on linear codes</H3> lower bound: {lower} upper bound: {upper} '
            f'<B>Construction</B> {construction} last modified: {modified} '
            f'<B>Notes</B> All codes were constructed using MAGMA.').encode('latin-1')


class ParseTests(unittest.TestCase):
    def test_table_cells_with_single_values_and_ranges(self):
        entries = v03_targets.parse_table(3, TABLE)
        self.assertEqual(entries[0], dict(q=3, n=20, k=8, lower=7, upper=7))
        self.assertEqual(entries[1], dict(q=3, n=22, k=8, lower=9, upper=10))

    def test_entry_page_bounds_date_and_ai_terms(self):
        details = v03_targets.parse_entry(entry_page(9, 10, '2001-12-17'))
        self.assertEqual((details['lower'], details['upper'], details['last_modified']), (9, 10, '2001-12-17'))
        self.assertEqual(details['ai_terms'], [])
        flagged = v03_targets.parse_entry(entry_page(9, 10, '2019-01-01', 'found by AlphaEvolve search'))
        self.assertEqual(flagged['ai_terms'], ['AlphaEvolve'])

    def test_notes_boilerplate_is_not_scanned(self):
        page = entry_page(9, 10, '2001-12-17').replace(b'MAGMA', b'machine learning')
        self.assertEqual(v03_targets.parse_entry(page)['ai_terms'], [])


class RuleTests(unittest.TestCase):
    def test_qualifying_entries(self):
        entries = v03_targets.parse_table(3, TABLE)
        self.assertEqual([(e['n'], e['k']) for e in entries if v03_targets.qualifies(e)],
                         [(22, 8), (50, 14)])  # closed, beyond 4k, and above the k limit are excluded

    def test_rejections(self):
        entry = dict(q=3, n=22, k=8, lower=9, upper=10)
        parse = v03_targets.parse_entry
        self.assertIsNone(v03_targets.entry_rejection(entry, parse(entry_page(9, 10, '2001-12-17'))))
        self.assertIn('differ', v03_targets.entry_rejection(entry, parse(entry_page(10, 10, '2001-12-17'))))
        self.assertIn('2023', v03_targets.entry_rejection(entry, parse(entry_page(9, 10, '2024-05-01'))))
        self.assertIn('LLM', v03_targets.entry_rejection(
            entry, parse(entry_page(9, 10, '2010-01-01', 'LLM-guided search'))))

    def test_selection_is_seeded_and_stops_at_the_target_count(self):
        entries = [dict(q=3, n=n, k=8, lower=1, upper=2) for n in range(16, 33)]
        snapshot = dict(retrieved='2026-10-10T00:00:00+00:00', entries=entries)
        pages = {n: entry_page(1, 2, '2024-01-01' if n % 3 == 0 else '2001-01-01') for n in range(16, 33)}
        first = v03_targets.select(snapshot, lambda q, n, k: pages[n])
        second = v03_targets.select(snapshot, lambda q, n, k: pages[n])
        self.assertEqual(first['targets'], second['targets'])
        self.assertEqual(len(first['targets']), v03_targets.TARGET_COUNT)
        self.assertTrue(all(t['n'] % 3 for t in first['targets']))
        self.assertFalse(first['fallback_required'])

    def test_too_few_targets_requires_the_fallback(self):
        snapshot = dict(retrieved='x', entries=[dict(q=3, n=20, k=8, lower=1, upper=2)])
        result = v03_targets.select(snapshot, lambda q, n, k: entry_page(1, 2, '2001-01-01'))
        self.assertTrue(result['fallback_required'])


if __name__ == '__main__':
    unittest.main()
