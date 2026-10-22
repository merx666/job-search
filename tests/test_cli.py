import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from openpyxl import load_workbook
import job_scout
from jobscout.core import build_report, digest
from jobscout.report import write_report
from test_core import plan, job

ROOT=Path(__file__).resolve().parent.parent

class CliTests(unittest.TestCase):
    def test_confirmation_before_any_browser_operation(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'plan.json';p.write_text(json.dumps(plan()))
            with patch.object(sys,'argv',['job_scout.py','scan','--plan',str(p),'--confirm','wrong','--out',t]),patch('jobscout.browser.launcher') as browser:
                with self.assertRaises(ValueError):job_scout.main()
                browser.assert_not_called()
    def test_plan_does_not_touch_browser(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)/'p.json'
            with patch.object(sys,'argv',['job_scout.py','plan','--keyword','电工','--city','苏州','--out',str(out)]),patch('jobscout.browser.launcher') as browser,patch('builtins.print'):
                self.assertEqual(job_scout.main(),0);browser.assert_not_called()
            self.assertEqual(json.loads(out.read_text())['keywords'],['电工'])
    def test_malformed_status_and_urls_rejected(self):
        for s in ({'boss':{'status':'magic'}},{'boss':{'status':'ok','url':'javascript:alert(1)'}},{'yupao':{'status':'ok'}}):
            with self.assertRaises(ValueError):job_scout.validate_statuses(s,plan())
    def test_report_html_and_excel_injection(self):
        p=plan();raw=job(company='=HYPERLINK("https://evil.test")',title='财务分析师 </script><script>alert(1)</script>')
        with tempfile.TemporaryDirectory() as t:
            write_report(build_report([raw],p),p,{'boss':{'status':'ok','url':'javascript:alert(1)'}},t)
            html=(Path(t)/'jobs.html').read_text()
            self.assertNotIn('</script><script>alert(1)</script>',html)
            self.assertIn('\\u003c/script',html)
            self.assertNotIn('javascript:alert',html)
            wb=load_workbook(Path(t)/'jobs.xlsx');self.assertEqual(wb['优先投递']['B2'].data_type,'s');self.assertTrue(wb['优先投递']['B2'].value.startswith("'="))
    def test_empty_report(self):
        with tempfile.TemporaryDirectory() as t:
            meta=write_report([],plan(),{'boss':{'status':'login_required'}},t)
            self.assertEqual(meta['status'],'partial');self.assertEqual(meta['counts']['shortlist'],0)
            self.assertTrue((Path(t)/'jobs.xlsx').is_file())
    def test_import_does_not_claim_coverage(self):
        with tempfile.TemporaryDirectory() as t:
            t=Path(t);(t/'plan.json').write_text(json.dumps(plan()));(t/'raw.json').write_text(json.dumps([job()]))
            with patch.object(sys,'argv',['job_scout.py','report','--plan',str(t/'plan.json'),'--input',str(t/'raw.json'),'--out',str(t/'out')]),patch('builtins.print'):
                self.assertEqual(job_scout.main(),3)
            statuses=json.loads((t/'out/summary.json').read_text())['statuses']
            self.assertEqual(statuses['boss']['status'],'imported');self.assertEqual(statuses['liepin']['status'],'not_scanned')
    def test_install_never_overwrites(self):
        from install import install
        with tempfile.TemporaryDirectory() as t:
            existing=Path(t)/'job-scout';existing.mkdir();(existing/'keep.txt').write_text('keep')
            with self.assertRaises(ValueError):install(t)
            self.assertEqual((existing/'keep.txt').read_text(),'keep')
    def test_duplicate_install_reuses_link(self):
        from install import install
        with tempfile.TemporaryDirectory() as t:
            a=install(t);self.assertEqual(install(t),a);self.assertTrue(a.is_symlink())
    def test_resume_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as t:
            t=Path(t);p=plan();(t/'p.json').write_text(json.dumps(p));(t/'raw-jobs.json').write_text('keep')
            with patch.object(sys,'argv',['job_scout.py','scan','--plan',str(t/'p.json'),'--confirm',digest(p),'--out',str(t)]),patch('jobscout.browser.launcher',return_value='fake'):
                with self.assertRaises(ValueError):job_scout.main()
            self.assertEqual((t/'raw-jobs.json').read_text(),'keep')
    def test_anti_bot_cooldown_after_two_immediate_blanks(self):
        with tempfile.TemporaryDirectory() as t:
            t=Path(t);p=plan(platforms=['boss']);(t/'p.json').write_text(json.dumps(p))
            blank={'status':'browser_error','jobs':[],'pages':0,'blanked':True,'immediate':True}
            with patch.object(sys,'argv',['job_scout.py','scan','--plan',str(t/'p.json'),'--confirm',digest(p),'--out',str(t/'out')]),patch('jobscout.browser.launcher',return_value='fake'),patch('jobscout.browser.inspect',return_value={'status':'ready','login':'signed_in','url':'https://www.zhipin.com/'}),patch('jobscout.browser.scan',side_effect=[blank,dict(blank)]) as scan,patch('jobscout.browser.finish'),patch('time.sleep'),patch('builtins.print'):
                self.assertEqual(job_scout.main(),3)
                self.assertEqual(scan.call_count,2)
                self.assertEqual(scan.call_args.args[1:4],('boss','财务分析师','上海'))
            s=json.loads((t/'out/platform-status.json').read_text())
            self.assertEqual(s['boss']['status'],'anti_bot_cooldown')
            actions=json.loads((t/'out/next-actions.json').read_text())
            self.assertEqual(actions['paused'],['boss']);self.assertEqual(actions['needs_user'],[])
    def test_second_attempt_recovers_after_one_immediate_blank(self):
        with tempfile.TemporaryDirectory() as t:
            t=Path(t);p=plan(platforms=['boss']);(t/'p.json').write_text(json.dumps(p))
            blank={'status':'browser_error','jobs':[],'pages':0,'blanked':True,'immediate':True}
            ok={'status':'ok','jobs':[job(platform='boss')],'pages':1}
            with patch.object(sys,'argv',['job_scout.py','scan','--plan',str(t/'p.json'),'--confirm',digest(p),'--out',str(t/'out')]),patch('jobscout.browser.launcher',return_value='fake'),patch('jobscout.browser.inspect',return_value={'status':'ready','login':'signed_in','url':'https://www.zhipin.com/'}),patch('jobscout.browser.scan',side_effect=[blank,ok]) as scan,patch('jobscout.browser.finish'),patch('time.sleep'),patch('builtins.print'):
                self.assertEqual(job_scout.main(),3)
                self.assertEqual(scan.call_count,2)
            s=json.loads((t/'out/platform-status.json').read_text())
            self.assertEqual(s['boss']['status'],'ok');self.assertEqual(s['boss']['jobs'],1)
            self.assertEqual(s['boss']['queries'][0]['status'],'ok')
    def test_blanked_scratch_inspection_does_not_block_automatic_scan(self):
        with tempfile.TemporaryDirectory() as t:
            t=Path(t);p=plan(platforms=['boss']);(t/'p.json').write_text(json.dumps(p))
            ok={'status':'ok','jobs':[job(platform='boss')],'pages':1}
            with patch.object(sys,'argv',['job_scout.py','scan','--plan',str(t/'p.json'),'--confirm',digest(p),'--out',str(t/'out')]),patch('jobscout.browser.launcher',return_value='fake'),patch('jobscout.browser.inspect',return_value={'status':'browser_error','login':'unknown','url':'about:blank'}),patch('jobscout.browser.scan',return_value=ok) as scan,patch('jobscout.browser.finish'),patch('builtins.print'):
                self.assertEqual(job_scout.main(),3)
                scan.assert_called_once()
            s=json.loads((t/'out/platform-status.json').read_text())
            self.assertEqual(s['boss']['status'],'ok');self.assertEqual(s['boss']['jobs'],1)
    def test_only_genuine_user_tabs_are_reused_for_collection(self):
        with tempfile.TemporaryDirectory() as t:
            t=Path(t);p=plan();(t/'p.json').write_text(json.dumps(p))
            states=[{'status':'ready','login':'signed_in','url':'https://www.zhipin.com/','tab_id':99,'reused_tab':True},
                    {'status':'ready','login':'signed_in','url':'https://www.liepin.com/','tab_id':98,'reused_tab':False}]
            with patch.object(sys,'argv',['job_scout.py','scan','--plan',str(t/'p.json'),'--confirm',digest(p),'--out',str(t/'out')]),patch('jobscout.browser.launcher',return_value='fake'),patch('jobscout.browser.inspect',side_effect=states),patch('jobscout.browser.scan',return_value={'status':'empty','jobs':[],'pages':1}) as scan,patch('jobscout.browser.finish'),patch('builtins.print'):
                job_scout.main()
            self.assertEqual(scan.call_args_list[0].kwargs['tab_id'],99)
            self.assertIsNone(scan.call_args_list[1].kwargs['tab_id'])
    def test_login_skips_platform_and_continues_others(self):
        with tempfile.TemporaryDirectory() as t:
            t=Path(t);p=plan();(t/'p.json').write_text(json.dumps(p))
            states=[{'status':'login_required','login':'signed_out'},{'status':'ready','login':'unknown'}]
            with patch.object(sys,'argv',['job_scout.py','scan','--plan',str(t/'p.json'),'--confirm',digest(p),'--out',str(t/'out')]),patch('jobscout.browser.launcher',return_value='fake'),patch('jobscout.browser.inspect',side_effect=states),patch('jobscout.browser.scan',return_value={'status':'empty','jobs':[],'pages':1}) as scan,patch('jobscout.browser.finish'),patch('time.sleep'),patch('builtins.print'):
                self.assertEqual(job_scout.main(),3)
                self.assertEqual(scan.call_count,1);self.assertEqual(scan.call_args.args[1],'liepin')
            s=json.loads((t/'out/platform-status.json').read_text());self.assertEqual(s['boss']['status'],'login_required');self.assertEqual(s['liepin']['status'],'empty')
    def test_package_manifest_no_local_state(self):
        from build_package import release_files
        paths=release_files()
        self.assertTrue(paths)
        self.assertFalse(any('.venv' in p.parts or 'runs' in p.parts or p.suffix=='.pyc' for p in paths))

if __name__=='__main__':unittest.main()
