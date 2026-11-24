"""Execution edge cases for the daily-bar research model."""

import unittest

import numpy as np
import pandas as pd

from analyze import simulate


class ExecutionTest(unittest.TestCase):
    def setUp(self):
        self.events = pd.DataFrame({'event_id': range(4), 'liquidity': [20_000_000] * 4})
        self.paths = pd.DataFrame({
            'event_id': np.repeat(range(4), 10),
            'traded': True,
            'limit_open_up': False,
            'limit_open_down': False,
            'isST': '0',
            'open': 10.,
            'adj_open': 10.,
            'bar_date': pd.Timestamp('2024-01-01'),
        })

    def test_entry_limit_exit_delay_and_unresolved(self):
        self.paths.loc[3, 'adj_open'] = 11.
        self.paths.loc[10, 'limit_open_up'] = True
        self.paths.loc[23, 'limit_open_down'] = True
        self.paths.loc[33:39, 'traded'] = False
        result = simulate(self.events, self.paths, .001)

        self.assertEqual(result.execution.tolist(), ['sold', 'entry_block', 'delayed', 'unresolved'])
        self.assertEqual(result.exit_offset.loc[2], 5.)
        self.assertEqual(result.net.loc[1], 0.)
        sale_fee = 5 + 9900 * (.0005 + .001)
        buy_fee = 5 + 9000 * .001
        self.assertAlmostEqual(result.net.loc[0], (9900 - 9000 - sale_fee - buy_fee) / 10000)
        self.assertAlmostEqual(result.net.loc[3], -(9000 + buy_fee) / 10000)

    def test_missing_entry_price_cannot_fill(self):
        self.paths['traded'] = self.paths['traded'].astype('boolean')
        self.paths.loc[0, ['traded', 'open', 'adj_open']] = [pd.NA, np.nan, np.nan]
        result = simulate(self.events, self.paths, .001)
        self.assertEqual(result.execution.loc[0], 'entry_block')
        self.assertEqual(result.net.loc[0], 0.)

    def test_participation_cap_can_block_a_full_lot(self):
        self.events.loc[0, 'liquidity'] = 999_999
        result = simulate(self.events, self.paths, .001)
        self.assertEqual(result.execution.loc[0], 'liquidity')
        self.assertEqual(result.net.loc[0], 0.)


if __name__ == '__main__':
    unittest.main()
