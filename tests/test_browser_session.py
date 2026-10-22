import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from jobscout import browser
from jobscout.workflow import next_actions
from test_core import plan

class BrowserSessionTests(unittest.TestCase):
    def test_existing_tab_acquired_without_new_navigation(self):
        inv={'tabs':[{'tabId':8,'url':'https://www.zhipin.com/web/geek/jobs','state':'available'}],'truncated':False}
        with patch.object(browser,'command',return_value=inv),patch.object(browser,'node',return_value={'status':'ready','login':'signed_in','url':inv['tabs'][0]['url']}) as node:
            result=browser.inspect('t','boss')
        self.assertEqual(node.call_args.kwargs['tab_id'],8)
        self.assertNotIn('.goto(',node.call_args.args[1]);self.assertNotIn('newPage',node.call_args.args[1])
        self.assertTrue(result['reused_tab']);self.assertEqual(result['tab_id'],8)
    def test_logged_in_tab_wins_over_login_landing(self):
        inv={'tabs':[{'tabId':1,'url':'https://www.zhipin.com/','state':'available'},{'tabId':2,'url':'https://www.zhipin.com/web/geek/jobs','state':'available'}],'truncated':False}
        with patch.object(browser,'command',return_value=inv),patch.object(browser,'node',return_value={'status':'ready','login':'signed_in'}) as n:
            browser.inspect('t','boss')
        self.assertEqual(n.call_args.kwargs['tab_id'],2)
    def test_other_task_owned_tab_not_replaced_with_fresh_tab(self):
        inv={'tabs':[{'tabId':8,'url':'https://www.zhipin.com/web/geek/jobs','state':'claimed'}],'truncated':False}
        with patch.object(browser,'command',return_value=inv),patch.object(browser,'node') as n:
            s=browser.inspect('t','boss')
        self.assertEqual(s['status'],'browser_busy');n.assert_not_called()
    def test_all_inventory_pages_read_before_open(self):
        replies=[{'tabs':[],'truncated':True,'nextCursor':'more'},{'tabs':[{'tabId':8,'url':'https://www.zhipin.com/web/geek/jobs','state':'available'}],'truncated':False}]
        with patch.object(browser,'command',side_effect=replies) as c,patch.object(browser,'node',return_value={'status':'ready','login':'signed_in'}) as n:
            browser.inspect('t','boss')
        self.assertEqual(c.call_args_list[1].args[0][0],'tabs');self.assertEqual(n.call_args.kwargs['tab_id'],8)
    def test_incomplete_inventory_does_not_open_more_tabs(self):
        with patch.object(browser,'command',return_value={'tabs':[],'truncated':True}),patch.object(browser,'node') as n:
            with self.assertRaises(browser.TabbitError):browser.inspect('t','boss')
        n.assert_not_called()
    def test_auth_wall_in_one_tab_does_not_ignore_another_ready_tab(self):
        inv={'tabs':[{'tabId':1,'url':'https://www.zhipin.com/web/geek/jobs','state':'available'},{'tabId':2,'url':'https://www.zhipin.com/','state':'available'}],'truncated':False}
        with patch.object(browser,'command',return_value=inv),patch.object(browser,'node',side_effect=[{'status':'login_required','login':'signed_out'},{'status':'ready','login':'signed_in'}]):
            result=browser.inspect('t','boss')
        self.assertEqual(result['status'],'ready');self.assertEqual(result['tab_id'],2)
    def test_detached_tab_is_agent_diagnostic_not_login_or_reload(self):
        inv={'tabs':[{'tabId':8,'url':'https://www.zhipin.com/web/geek/jobs','state':'available'}],'truncated':False}
        with patch.object(browser,'command',return_value=inv),patch.object(browser,'node',side_effect=browser.TabbitError('The acquired entry tab is no longer attached')) as n:
            s=browser.inspect('t','boss')
        self.assertEqual(s['status'],'browser_error');self.assertEqual(s['login'],'unknown')
        self.assertEqual(n.call_count,1);self.assertNotIn('.goto(',n.call_args.args[1])

    def test_scan_prefers_observed_tab_and_marks_reuse(self):
        with patch.object(browser,'node',return_value={}) as n:
            browser.scan('t','boss','会计','上海',1,tab_id=8)
        self.assertEqual(n.call_args.kwargs['tab_id'],8)
        self.assertIn('"reuse": true',n.call_args.args[1])
    def test_scan_without_tab_opens_fresh_page(self):
        with patch.object(browser,'node',return_value={}) as n:
            browser.scan('t','boss','会计','上海',1)
        self.assertIsNone(n.call_args.kwargs['tab_id'])
        self.assertIn('"reuse": false',n.call_args.args[1])
    def test_browser_error_and_wrong_role_are_agent_work(self):
        for status in ('browser_error','wrong_context','browser_busy','needs_inspection'):
            a=next_actions(plan(platforms=['boss']),[],{'boss':{'status':status,'login':'unknown'}})
            self.assertEqual(a['needs_user'],[]);self.assertEqual(a['needs_agent'],['boss'])
    def test_anti_bot_cooldown_pauses_platform_without_user_work(self):
        a=next_actions(plan(platforms=['boss']),[],{'boss':{'status':'anti_bot_cooldown','login':'signed_in'}})
        self.assertEqual(a['needs_user'],[]);self.assertEqual(a['needs_agent'],[])
        self.assertEqual(a['paused'],['boss'])
        self.assertEqual(a['platforms'][0]['action'],'pause_platform')
        self.assertIn('about:blank',a['platforms'][0]['message'])
        self.assertIn('不是未登录',a['platforms'][0]['message'])
    def test_error_layer_wins_over_stale_login_flag(self):
        for status,expected in [('wrong_context','inspect_existing_tab'),('model_rate_limited','pause_model'),('platform_rate_limited','pause_platform')]:
            a=next_actions(plan(platforms=['boss']),[],{'boss':{'status':status,'login':'signed_out'}})
            self.assertEqual(a['needs_user'],[]);self.assertEqual(a['platforms'][0]['action'],expected)
    def test_model_pause_defers_other_platforms(self):
        a=next_actions(plan(),[],{'boss':{'status':'model_rate_limited'},'liepin':{'status':'not_scanned'}})
        self.assertTrue(a['execution_paused']);self.assertEqual(a['needs_agent'],[])
        self.assertEqual(a['deferred_until_resume'],['liepin'])

    def test_model_limit_does_not_create_platform_login_work(self):
        a=next_actions(plan(platforms=['boss']),[],{'boss':{'status':'model_rate_limited','login':'unknown'}})
        self.assertEqual(a['needs_user'],[]);self.assertEqual(a['needs_agent'],[])
        self.assertEqual(a['paused'],['boss']);self.assertFalse(a['can_deliver_final'])
    def test_second_process_cannot_run_browser_loop(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'JOB_SCOUT_STATE_DIR':tmp}):
            with browser.run_lock():
                code='from jobscout.browser import run_lock;\nwith run_lock(): print("SECOND_STARTED")'
                r=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True)
                self.assertNotEqual(r.returncode,0);self.assertNotIn('SECOND_STARTED',r.stdout)
            with browser.run_lock():pass

if __name__=='__main__':unittest.main()
