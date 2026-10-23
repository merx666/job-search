import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import job_search
from jobscout.core import build_report, digest, validate_plan
from jobscout.workflow import next_actions
from test_core import plan, job


class BudgetTests(unittest.TestCase):
    def progress(self, state, **limits):
        p = plan(platforms=['boss'], **limits)
        jobs = build_report([job(publish_time='')], p)
        return next_actions(p, jobs, {'boss': {'status': 'ok', **state}})

    def test_defaults_scale_for_queries_and_targets(self):
        self.assertEqual(plan()['max_pages_per_platform'], 6)
        self.assertEqual(plan()['max_details_per_platform'], 30)
        p = plan(keywords=['财务', '会计', '审计'], cities=['上海', '北京'])
        self.assertEqual(p['max_pages_per_platform'], 12)
        p = plan(platform_job_counts={'boss': 20})
        self.assertEqual((p['max_pages_per_platform'], p['max_details_per_platform']), (12, 120))
        p = plan(jobs_per_platform=100)
        self.assertEqual((p['max_pages_per_platform'], p['max_details_per_platform']), (60, 600))

    def test_old_normalized_plan_and_digest_are_unchanged(self):
        p = plan(max_pages_per_platform=3, max_details_per_platform=10)
        self.assertEqual(validate_plan(p), p)
        self.assertEqual(digest(validate_plan(p)), digest(p))
        for fields in ({'max_pages_per_platform': 0}, {'max_pages_per_platform': True},
                       {'max_pages_per_platform': 61}, {'max_details_per_platform': 601}):
            with self.assertRaises(ValueError):
                plan(**fields)

    def test_result_cap_still_uses_existing_candidates(self):
        a = self.progress({'stop_reason': 'budget_exhausted', 'queries': [{'pages': 6}],
                           'details_attempted': 10, 'details_read': 6})
        self.assertFalse(a['can_deliver_final'])
        row = a['platforms'][0]
        self.assertEqual(row['action'], 'verify_details')
        self.assertEqual(row['budget']['details']['remaining'], 20)
        self.assertEqual(len(row['detail_queue']), 1)

    def test_detail_cap_still_uses_remaining_result_pages(self):
        a = self.progress({'stop_reason': 'budget_exhausted', 'pages_read': 3,
                           'details_attempted': 30})
        self.assertEqual(a['platforms'][0]['action'], 'collect_more')
        self.assertFalse(a['can_deliver_final'])

    def test_both_caps_allow_honest_partial_delivery(self):
        a = self.progress({'stop_reason': 'budget_exhausted', 'pages_read': 3,
                           'details_attempted': 10, 'details_read': 6},
                          max_pages_per_platform=3, max_details_per_platform=10)
        self.assertTrue(a['can_deliver_final'])
        self.assertFalse(a['complete'])
        self.assertEqual(a['qualified_total'], 0)
        self.assertIn('成功读取 6', a['platforms'][0]['message'])

    def test_bare_stop_flag_is_not_evidence(self):
        for s in ({'stop_reason': 'budget_exhausted'},
                  {'stop_reason': 'budget_exhausted', 'pages_read': 3}):
            a = self.progress(s)
            self.assertEqual(a['platforms'][0]['action'], 'audit_budget')
            self.assertFalse(a['can_deliver_final'])

    def test_no_more_listings_does_not_skip_existing_details(self):
        a = self.progress({'stop_reason': 'results_exhausted', 'pages_read': 1,
                           'details_attempted': 0})
        self.assertEqual(a['platforms'][0]['action'], 'verify_details')
        a = self.progress({'stop_reason': 'results_exhausted', 'pages_read': 1,
                           'details_attempted': 1, 'detail_urls': [job()['link']]})
        self.assertTrue(a['can_deliver_final'])
        self.assertFalse(a['complete'])

    def test_results_exhausted_needs_recorded_search_even_without_candidates(self):
        p = plan(platforms=['boss'])
        for counters in ({}, {'pages_read': 1}, {'details_attempted': 0},
                         {'pages_read': 0, 'details_attempted': 0}):
            for jobs in ([], build_report([job()], p)):
                state = {'status': 'ok', 'stop_reason': 'results_exhausted', **counters}
                a = next_actions(p, jobs, {'boss': state})
                self.assertEqual(a['platforms'][0]['action'], 'audit_budget')
                self.assertFalse(a['can_deliver_final'])
        a = next_actions(p, [], {'boss': {'status': 'empty', 'stop_reason': 'results_exhausted',
                                          'queries': [{'pages': 1}], 'details_attempted': 0}})
        self.assertTrue(a['can_deliver_final'])
        self.assertFalse(a['complete'])

    def test_queue_omits_rejected_and_visited_candidates(self):
        p = plan(platforms=['boss'])
        raw = [job(id=str(i), link=f'https://www.zhipin.com/job_detail/{i}.html',
                   publish_time='', city='北京' if i == 9 else '上海') for i in range(10)]
        s = {'boss': {'status': 'ok', 'pages_read': 1, 'details_attempted': 1,
                      'detail_urls': [raw[0]['link']]}}
        a = next_actions(p, build_report(raw, p), s)
        urls = [j['url'] for j in a['platforms'][0]['detail_queue']]
        self.assertEqual(len(urls), 5)
        self.assertNotIn(raw[0]['link'], urls)
        self.assertNotIn(raw[9]['link'], urls)

    def test_invalid_accounting_rejected(self):
        for fields in ({'details_attempted': -1}, {'details_attempted': True},
                       {'details_attempted': 2, 'details_read': 3},
                       {'queries': [{'pages': '3'}]},
                       {'queries': [{'pages': 2}], 'pages_read': 3},
                       {'details_attempted': 1, 'detail_urls': ['https://evil.test/x']},
                       {'detail_urls': [job()['link']]}):
            with self.assertRaises(ValueError):
                job_search.validate_statuses({'boss': {'status': 'ok', **fields}}, plan())

    def test_strict_unknowns_remain_excluded_but_can_be_verified(self):
        p = plan(platforms=['boss'], unknown_policy='exclude')
        jobs = build_report([job(publish_time=''), job(id='2', publish_time='')], p)
        a = next_actions(p, jobs, {'boss': {'status': 'ok', 'queries': [{'pages': 1}], 'details_attempted': 0}})
        self.assertEqual(a['qualified_total'], 0)
        self.assertTrue(all(j['bucket'] == 'excluded' for j in jobs))
        self.assertEqual(a['platforms'][0]['action'], 'verify_details')
        self.assertEqual(len(a['platforms'][0]['detail_queue']), 1)

    def test_blank_retry_cannot_exceed_confirmed_page_cap(self):
        for cap, calls in [(1, 1), (2, 2)]:
            with tempfile.TemporaryDirectory() as t:
                p = plan(platforms=['boss'], max_pages_per_platform=cap)
                source, out = Path(t)/'p.json', Path(t)/'scan'
                source.write_text(json.dumps(p))
                args = ['job_search.py', 'scan', '--plan', str(source), '--confirm', digest(p), '--out', str(out)]
                blank = {'status': 'browser_error', 'jobs': [], 'pages': 0, 'immediate': True}
                with patch.object(sys, 'argv', args), patch('builtins.print'), patch('time.sleep'), \
                     patch('jobscout.browser.launcher'), patch('jobscout.browser.finish'), \
                     patch('jobscout.browser.inspect', return_value={'status': 'ready', 'login': 'signed_in'}), \
                     patch('jobscout.browser.scan', return_value=blank) as scan:
                    self.assertEqual(job_search.main(), 3)
                self.assertEqual(scan.call_count, calls)
                s = json.loads((out/'platform-status.json').read_text())['boss']
                self.assertEqual(sum(q['pages'] for q in s['queries']), cap)

    def test_plan_budget_flags_are_offline_and_explicit(self):
        with tempfile.TemporaryDirectory() as t:
            source, out = Path(t)/'old.json', Path(t)/'new.json'
            p = plan(max_pages_per_platform=3, max_details_per_platform=10)
            source.write_text(json.dumps(p))
            base = ['job_search.py', 'plan', '--input', str(source), '--out', str(out)]
            with patch('jobscout.browser.launcher') as browser, patch('builtins.print'):
                for extra, expected in [(['--count', '10'], (3, 10)),
                                        (['--auto-budget'], (6, 30)),
                                        (['--auto-budget', '--pages', '9', '--details', '40'], (9, 40))]:
                    with patch.object(sys, 'argv', base + extra):
                        self.assertEqual(job_search.main(), 0)
                    new = json.loads(out.read_text())
                    self.assertEqual((new['max_pages_per_platform'], new['max_details_per_platform']), expected)
                    self.assertEqual(new['keywords'], p['keywords'])
                    self.assertNotEqual(digest(new), digest(p))
                browser.assert_not_called()

    def test_scan_covers_each_query_once_before_detail_work(self):
        with tempfile.TemporaryDirectory() as t:
            p = plan(platforms=['boss'], keywords=['财务', '会计', '审计'])
            source, out = Path(t)/'p.json', Path(t)/'scan'
            source.write_text(json.dumps(p))
            args = ['job_search.py', 'scan', '--plan', str(source), '--confirm', digest(p), '--out', str(out)]
            with patch.object(sys, 'argv', args), patch('builtins.print'), patch('time.sleep'), \
                 patch('jobscout.browser.launcher'), patch('jobscout.browser.finish'), \
                 patch('jobscout.browser.inspect', return_value={'status': 'ready', 'login': 'signed_in'}), \
                 patch('jobscout.browser.scan', return_value={'status': 'ok', 'jobs': [job(publish_time='')], 'pages': 1}) as scan:
                self.assertEqual(job_search.main(), 3)
            self.assertEqual(scan.call_count, 3)
            self.assertTrue(all(call.args[4] == 1 for call in scan.call_args_list))
            a = json.loads((out/'next-actions.json').read_text())
            self.assertEqual(a['platforms'][0]['budget']['pages']['used'], 3)
            self.assertEqual(a['platforms'][0]['action'], 'verify_details')


if __name__ == '__main__':
    unittest.main()
