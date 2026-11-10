"""The report must not confuse parser execution or zero times with success."""
import copy,unittest
from run_probe import verdict
from make_cases import cases


class ProbeTests(unittest.TestCase):
    def test_synthetic_times_only_match_complete_finite_evidence(self):
        expected=[[1.,3.],[3.,5.]]
        good={'parser_available':True,'parsed':True,'lines':[{'start':1.,'end':3.},{'start':3.,'end':5.}]}
        self.assertEqual(verdict(good,expected),'synthetic_times_match')
        for key,value in [('parser_available',False),('parsed',False),('error',{'code':1}),('lines',[]),
                          ('lines',[{'start':0,'end':0},{'start':0,'end':0}]),('lines',[{'start':True,'end':3},{'start':3,'end':5}]),
                          ('lines',[{'start':float('nan'),'end':3},{'start':3,'end':5}])]:
            bad=copy.deepcopy(good);bad[key]=value
            with self.subTest(key=key,value=value):self.assertNotEqual(verdict(bad,expected),'synthetic_times_match')

    def test_negative_control_and_unavailable_parser_are_distinct(self):
        self.assertEqual(verdict({'parser_available':False},None),'parser_unavailable')
        self.assertEqual(verdict({'parser_available':True,'parsed':False},None),'negative_control_rejected')
        self.assertEqual(verdict({'parser_available':True,'parsed':True},None),'negative_control_accepted')

    def test_cases_are_bounded_synthetic_and_keep_the_same_cue_times(self):
        samples=cases();self.assertEqual(len(samples),5)
        self.assertEqual(len({s['name'] for s in samples}),5)
        for item in samples:
            self.assertLess(len(item['xml']),16384);self.assertNotIn('<!DOCTYPE',item['xml'])
            if item['expected'] is not None:self.assertEqual(item['expected'],[[1.,3.],[3.,5.]])


if __name__=='__main__':unittest.main()
