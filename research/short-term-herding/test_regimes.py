"""Check correlations, ties and execution denominators on controlled fixtures."""
import unittest

import pandas as pd

from regimes import metrics


class FactorMetricsTest(unittest.TestCase):
    def test_rank_groups_are_fixed_before_open_and_keep_blocked_entries(self):
        day = pd.Timestamp('2025-01-02')
        panel = pd.DataFrame({
            'date': day, 'factor': range(10), 'forward': [0., .01, .02, .03, .04, .05, .06, .07, .08, None],
            'net10': [.02] * 9 + [0.], 'net30': [.01] * 9 + [0.], 'net60': [0.] * 10,
            'execution': ['sold'] * 9 + ['entry_block'],
        })
        result = metrics(panel, 'factor', pd.Series([day]))
        self.assertAlmostEqual(result['rank_ic'], 1.)
        self.assertAlmostEqual(result['spread'], .075)
        self.assertEqual(result['top_signals'], 2)
        self.assertEqual(result['top_fill'], .5)
        self.assertEqual(result['top_net'][0], .01)

    def test_constant_factor_has_no_correlation_or_spread(self):
        day = pd.Timestamp('2025-01-02')
        panel = pd.DataFrame({
            'date': day, 'factor': [1.] * 5, 'forward': range(5),
            'net10': 0., 'net30': 0., 'net60': 0., 'execution': 'sold',
        })
        result = metrics(panel, 'factor', pd.Series([day]))
        self.assertEqual(result['ic_days'], 0)
        self.assertEqual(result['spread_days'], 0)


if __name__ == '__main__':
    unittest.main()
