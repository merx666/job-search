import unittest
from unittest.mock import patch
from jobscout import browser

class TransportTests(unittest.TestCase):
    def test_inline_result(self):
        with patch.object(browser,'command',return_value={'status':'succeeded','result':{'value':{'ok':1}}}):self.assertEqual(browser.node('t','return 1'),{'ok':1})
    def test_pending_reads_receipt_not_resubmit(self):
        replies=[{'status':'running'},{'status':'succeeded','result':{'type':'inline','value':{'ok':1}}}]
        with patch.object(browser,'command',side_effect=replies) as c:
            self.assertEqual(browser.node('t','return 1'),{'ok':1})
            self.assertEqual(c.call_args_list[0].args[0][0],'nodejs');self.assertEqual(c.call_args_list[1].args[0][0],'receipt')
            self.assertEqual(c.call_args_list[0].args[0][4],c.call_args_list[1].args[0][4])
    def test_resource_complete(self):
        replies=[{'status':'succeeded','result':{'resourceId':'r'}},{'data':'{"a":','nextOffset':5,'eof':False},{'data':'1}','eof':True}]
        with patch.object(browser,'command',side_effect=replies):self.assertEqual(browser.node('t','return 1'),{'a':1})
    def test_resource_truncation_is_error(self):
        replies=[{'status':'succeeded','result':{'resourceId':'r'}},{'data':'{"a":','nextOffset':0,'eof':False}]
        with patch.object(browser,'command',side_effect=replies):
            with self.assertRaises(browser.TabbitError):browser.node('t','return 1')
    def test_failed_and_empty_receipts_are_errors(self):
        for res in ({'status':'failed','result':{}},{'status':'succeeded','result':{}}):
            with patch.object(browser,'command',return_value=res):
                with self.assertRaises(browser.TabbitError):browser.node('t','return 1')
    def test_finish_failure_not_swallowed(self):
        with patch.object(browser,'command',return_value={'forcedCleanup':True}):
            with self.assertRaises(browser.TabbitError):browser.finish('t')
    def test_query_escaping_and_unknown_city(self):
        url=browser.search_url('boss','研发"; alert(1); //','上海');self.assertNotIn('"',url);self.assertIn('%22',url)
        with self.assertRaises(ValueError):browser.search_url('liepin','采购','不存在的城市')

    def test_host_429_is_not_replayed_or_misattributed_to_website(self):
        with patch.object(browser,'command',return_value={'status':'failed','result':{'error':'exceeded retry limit, last status: 429 Too Many Requests'}}) as c:
            with self.assertRaises(browser.TabbitError) as error:browser.node('t','return 1')
            self.assertEqual(error.exception.code,'host_rate_limited');self.assertEqual(c.call_count,1)
    def test_explicit_model_limit_is_not_login_error(self):
        with self.assertRaises(browser.TabbitError) as error:browser.raise_transport_error({'code':'MODEL_RATE_LIMITED','message':'429'})
        self.assertEqual(error.exception.code,'model_rate_limited')

if __name__=='__main__':unittest.main()
