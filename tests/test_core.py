import copy
import datetime as dt
import unittest
from jobscout.core import *

TZ=dt.timezone(dt.timedelta(hours=8))
def plan(**kw):return validate_plan({'keywords':['财务分析师'],'cities':['上海'],'platforms':['boss','liepin'],**kw})
def job(**kw):
    return {'platform':'boss','id':'1','title':'财务分析师','company':'测试公司','salary':'18-25K','city':'上海','publish_time':'3天前','hr_active':'在线',
      'source_url':'https://www.zhipin.com/web/geek/job','link':'https://www.zhipin.com/job_detail/1.html','captured_at':dt.datetime.now(TZ).isoformat(),'evidence':'财务分析师 18-25K 上海 3天前发布',**kw}
def rank(p=None,**kw):return build_report([job(**kw)],p or plan())[0]

class CoreTests(unittest.TestCase):
    def test_neutral_profile(self):
        p=plan();self.assertEqual(p['avoid_keywords'],[]);self.assertEqual(p['plus_keywords'],[]);self.assertEqual(p['fresh_days'],60)
        self.assertEqual(rank()['bucket'],'shortlist')
    def test_required_fields(self):
        for raw in ({},{'keywords':['财务'],'cities':[]},{'keywords':'财务','cities':['上海']}):
            with self.assertRaises(ValueError):validate_plan(raw)
    def test_bad_enum_and_unknown_fields(self):
        for extra in ({'platforms':['fake']},{'unknown_policy':'pass'},{'foo':'bar'},{'require_active':'yes'}):
            with self.assertRaises(ValueError):plan(**extra)
    def test_finite_salary_and_bounds(self):
        for kw in ({'salary_min_k':float('nan')},{'salary_min_k':-1},{'salary_min_k':30,'salary_max_k':10},{'fresh_days':True}):
            with self.assertRaises(ValueError):plan(**kw)
    def test_global_budget(self):
        p=plan(keywords=['财务','会计'],cities=['上海','北京'])
        self.assertEqual(p['max_pages_per_platform'],8)
        with self.assertRaises(ValueError):plan(keywords=['财务','会计'],cities=['上海','北京'],max_pages_per_platform=3)
    def test_proposal_not_searched_until_accepted(self):
        s={'title':'经营分析师','evidence':'负责预算','gap':'需要核实业务分析经验','accepted':False}
        p=plan(suggested_directions=[s]);self.assertNotIn(s['title'],p['keywords'])
        with self.assertRaises(ValueError):plan(keywords=['财务分析师','经营分析师'],suggested_directions=[s])
        s['accepted']=True
        self.assertIn(s['title'],plan(keywords=['财务分析师','经营分析师'],suggested_directions=[s])['keywords'])
    def test_digest_invalidates_changes(self):
        p=plan();q=plan(fresh_days=30);self.assertNotEqual(digest(p),digest(q))
        self.assertEqual(digest(p),digest(dict(reversed(list(p.items())))))
    def test_refresh_is_not_publish(self):
        j=rank(publish_time='',refresh_time='今天');self.assertEqual(j['bucket'],'review');self.assertIsNone(j['publish_age_days'])
    def test_old_and_unknown_policy(self):
        self.assertEqual(rank(publish_time='90天前')['bucket'],'excluded')
        self.assertEqual(rank(plan(unknown_policy='exclude'),publish_time='')['bucket'],'excluded')
    def test_city_is_hard(self):
        self.assertEqual(rank(city='北京')['bucket'],'excluded');self.assertEqual(rank(city='')['bucket'],'review')
    def test_salary_overlap(self):
        p=plan(salary_min_k=20,salary_max_k=30)
        self.assertEqual(rank(p,salary='15-19K')['bucket'],'excluded')
        self.assertEqual(rank(p,salary='18-25K')['bucket'],'review')
        self.assertEqual(rank(p,salary='20-40K')['bucket'],'shortlist')
        self.assertEqual(rank(p,salary='40-50K')['bucket'],'excluded')
    def test_salary_units(self):
        for txt,want in [('1.5-2万/月',(15,20)),('8000-12000元/月',(8,12)),('8千-1.2万',(8,12)),('18K',(18,18)),('20-30k·14薪',(20,30))]:
            self.assertEqual(salary_range(txt),want)
        for txt in ('300-500元/天','30-40万/年','100元/小时','20K以上','面议'):
            self.assertIsNone(salary_range(txt))
    def test_missing_salary_not_logout(self):
        j=rank(plan(salary_min_k=15),salary='');self.assertEqual(j['bucket'],'review');self.assertNotIn('登录',str(j['unknowns']))
    def test_active_preference_and_requirement(self):
        self.assertEqual(rank(hr_active='')['bucket'],'shortlist')
        self.assertEqual(rank(plan(require_active=True),hr_active='')['bucket'],'review')
        self.assertEqual(rank(plan(require_active=True),hr_active='30天前活跃')['bucket'],'excluded')
        self.assertEqual(rank(plan(require_active=True),hr_active='不在线')['bucket'],'review')
    def test_must_all_required_and_case_insensitive(self):
        p=plan(must_keywords=['预算','SQL'])
        self.assertEqual(rank(p,description='预算分析')['bucket'],'excluded')
        self.assertEqual(rank(p,description='')['bucket'],'review')
        self.assertEqual(rank(p,description='预算与 sql 分析')['bucket'],'shortlist')
    def test_qualifications(self):
        p=plan(education='本科',experience_years=3)
        self.assertEqual(rank(p,experience='5年以上',degree='本科')['bucket'],'excluded')
        self.assertEqual(rank(p,experience='3-5年',degree='硕士')['bucket'],'excluded')
        self.assertEqual(rank(p,experience='经验不限',degree='本科')['bucket'],'shortlist')
    def test_other_constraints(self):
        p=plan(employment_types=['全职'],industries=['制造'],company_sizes=['100-499'])
        self.assertEqual(rank(p)['bucket'],'review')
        self.assertEqual(rank(p,employment_type='兼职')['bucket'],'excluded')
        self.assertEqual(rank(plan(extra_requirements=['双休']))['bucket'],'review')
    def test_old_relative_evidence_ages(self):
        collected=(dt.datetime.now(TZ)-dt.timedelta(days=70)).isoformat()
        self.assertEqual(rank(captured_at=collected,publish_time='今天')['bucket'],'excluded')
        self.assertEqual(rank(plan(require_active=True),captured_at=(dt.datetime.now(TZ)-dt.timedelta(days=10)).isoformat(),hr_active='在线')['bucket'],'excluded')
    def test_zero_days_and_invalid_dates(self):
        today=dt.date(2026,10,14)
        for value in ('今天','刚刚','2小时前','2026-10-14'):self.assertEqual(age_days(value,today),0)
        self.assertEqual(age_days('2026-09-14',today),30)
        self.assertIsNone(age_days('2026-11-01',today));self.assertIsNone(age_days('2026-99-99',today));self.assertIsNone(age_days('活跃',today))
    def test_dedupe_newest_keeps_city_differences(self):
        old=job(captured_at=(dt.datetime.now(TZ)-dt.timedelta(days=2)).isoformat(),salary='10-12K')
        new=job(salary='20-25K');jobs=build_report([old,new],plan());self.assertEqual(len(jobs),1);self.assertEqual(jobs[0]['salary'],'20-25K')
        foreign=job(platform='liepin',link='https://www.liepin.com/job/1.shtml',source_url='https://www.liepin.com/')
        jobs=build_report([new,foreign],plan());self.assertEqual(len(jobs),2);self.assertTrue(all(j['duplicate_hint'] for j in jobs))
    def test_limit_reserve(self):
        jobs=build_report([job(id=str(i)) for i in range(3)],plan(jobs_per_platform=1))
        self.assertEqual([j['bucket'] for j in jobs],['shortlist','reserve','reserve'])
    def test_evidence_is_required(self):
        for change in ({'evidence':''},{'source_url':''},{'captured_at':'2026-10-14'},{'company':''}):
            with self.assertRaises(ValueError):rank(**change)
    def test_unsafe_urls(self):
        for val in ('javascript:alert(1)','https://evil.test/x','https://zhipin.com.evil.test','https://user:pw@zhipin.com/'):
            with self.assertRaises(ValueError):rank(link=val)
        self.assertEqual(safe_url('https://www.zhipin.com/job_detail/a.html','boss'),'https://www.zhipin.com/job_detail/a.html')
    def test_unplanned_platform(self):
        with self.assertRaises(ValueError):build_report([job(platform='liepin',link='https://www.liepin.com/',source_url='https://www.liepin.com/')],plan(platforms=['boss']))

if __name__=='__main__':unittest.main()
