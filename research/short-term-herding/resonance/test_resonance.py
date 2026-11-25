"""Test sector cycles without using limit-up qualification."""
import unittest
from types import SimpleNamespace

import pandas as pd

from group_cycles import conditions, episodes


def state(relative=.03,breadth=.60,lo=1.20,hi=1.22):
    return dict(relative5=relative,breadth5=breadth,
                concentration_lo=lo,concentration_hi=hi,
                max_height=0,members=30)


class ResonanceTest(unittest.TestCase):
    def test_no_limit_up_requirement(self):
        self.assertEqual(conditions(SimpleNamespace(**state())),(True,False))

    def test_confirmation_and_three_consecutive_retreat_days(self):
        days=pd.DataFrame({'date':pd.date_range('2026-07-01',periods=8,freq='B'),
                           'seq':range(1,9)})
        good=state()
        bad=state(-.01,.40,.98,1.02)
        # Old single-stock exit rules are deliberately absent.
        rows=[good,good,bad,good,bad,bad,bad,bad]
        panel=pd.DataFrame(rows)
        panel['seq']=days.seq
        result=episodes(panel,days)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['start'],2)
        self.assertEqual(result[0]['end'],7)
        self.assertEqual(result[0]['duration'],5)

    def test_amount_interval_does_not_trigger_unconfirmed_start(self):
        row=SimpleNamespace(**state(lo=1.13,hi=1.17))
        self.assertEqual(conditions(row),(False,False))

    def test_missing_session_interrupts_retreat_confirmation(self):
        days=pd.DataFrame({'date':pd.date_range('2026-07-01',periods=7,freq='B'),
                           'seq':range(1,8)})
        good=state()
        bad=state(-.01,.40,.98,1.02)
        panel=pd.DataFrame([good,good,bad,bad,bad,bad])
        panel['seq']=[1,2,3,5,6,7]
        result=episodes(panel,days)
        self.assertEqual(result[0]['end'],7)
        self.assertEqual(result[0]['missing_days'],1)


if __name__=='__main__':
    unittest.main()
