import unittest
from types import SimpleNamespace

import pandas as pd

from analyze_cycles import confirmed_reference, reconstruct, trade


class CohortTest(unittest.TestCase):
    def test_uses_compatible_previous_close_and_unique_ex_rights_reference(self):
        xs=[10.,11.,9.,10.5]
        ys=[30.,32.,28.,31.]
        self.assertEqual(confirmed_reference(xs,ys,10.,30.,.0001),(10.,'prior_raw_close'))
        self.assertEqual(confirmed_reference(xs,ys,10.2,30.,.0001),(10.,'unique_adjusted_tick'))

    def test_frozen_cohort_ends_on_second_breach(self):
        days=pd.DataFrame({'seq':list(range(1,6)),
                           'date':pd.date_range('2026-07-01',periods=5,freq='B'),
                           'height':4})
        a=set('abcdefghij')
        strict={1:a,2:a,3:set('abcde'),4:set('abcd'),5:set('abc')}
        cohorts={2:(sorted(a),1.4,1.5,[.2]*10,[3]*10)}
        episodes,amb=reconstruct(days,strict,{},cohorts)
        self.assertFalse(amb)
        self.assertEqual(len(episodes),1)
        self.assertEqual((episodes[0]['start'],episodes[0]['end']),(2,5))
        self.assertEqual([d['retained'] for d in episodes[0]['trajectory']],[10,5,4,3])

    def test_uncertain_concentration_cannot_trigger(self):
        days=pd.DataFrame({'seq':[1,2],'date':pd.date_range('2026-07-01',periods=2),
                           'height':[3,3]})
        core=set('abc')
        episodes,amb=reconstruct(days,{1:core,2:core},{},{2:(sorted(core),1.25,1.34,[.2]*3,[3]*3)})
        self.assertFalse(episodes)
        self.assertEqual(len(amb),1)

    def test_execution_blocks_limit_open_and_unknown_price_path(self):
        code='sz.000001'
        row=lambda **kw: SimpleNamespace(**(dict(valid=True,risk=False,open=10.,up=11.,down=9.,
                trading=True,amount_lo=1e8,liquidity=1e8,adj_open=10.)|kw))
        prices={(code,1):row(),(code,2):row(open=11.),(code,3):row(valid=False),
                (code,4):row()}
        self.assertEqual(trade(prices,code,2,4,10000.,1,4)['status'],'entry_block')
        prices[code,2]=row()
        self.assertEqual(trade(prices,code,2,4,10000.,1,4)['status'],'unknown_price_path')


if __name__=='__main__':
    unittest.main()
