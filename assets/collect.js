// Passive responses from a user-visible search, with ordinary UI pagination only.
// Platforms blank automation-created pages seconds after render; user-opened tabs
// are not blanked. So collection prefers the pre-opened tab (CFG.reuse) and never
// closes it, and any evidence captured before a blank stays in the result.
const reused = !!CFG.reuse;
const p = reused ? page : await context.newPage();
const records = [], pending = [];
let apiError = null, pagesRead = 0, preservePage = false;
const mapBoss = j => ({id:j.encryptJobId, title:j.jobName,company:j.brandName,salary:j.salaryDesc,
 city:j.cityName,district:j.areaDistrict,experience:j.jobExperience,degree:j.jobDegree,
 skills:j.skills||[],labels:j.jobLabels||[],industry:j.brandIndustry,scale:j.brandScaleName,
 hr_active:j.activeTimeDesc||(j.bossOnline?'在线':''),publish_time:j.publishTime||j.firstPublishTime||'',
 link:j.encryptJobId?'https://www.zhipin.com/job_detail/'+encodeURIComponent(j.encryptJobId)+'.html':'',
 evidence:JSON.stringify({title:j.jobName,company:j.brandName,salary:j.salaryDesc,city:j.cityName,active:j.activeTimeDesc})});
const mapLiepin = c => ({id:String(c.job?.jobId||c.job?.j||''),title:c.job?.title,company:c.comp?.compName,
 salary:c.job?.salary,city:(c.job?.dq||'').split('-')[0],district:(c.job?.dq||'').split('-').slice(1).join('-'),
 experience:c.job?.requireWorkYears,degree:c.job?.requireEduLevel,labels:c.job?.labels||[],
 industry:c.comp?.compIndustry,scale:c.comp?.compScale,link:c.job?.link,
 refresh_time:c.job?.refreshTime||'',publish_time:c.job?.publishTime||'',
 evidence:JSON.stringify({title:c.job?.title,company:c.comp?.compName,salary:c.job?.salary,city:c.job?.dq,refresh:c.job?.refreshTime})});
const listener = r => {
 const url = r.url();
 if (!(CFG.platform==='boss' ? url.includes('/wapi/zpgeek/search/joblist.json') : url.includes('pc-search-job')&&!url.includes('init'))) return;
 // Reading a response body on a page the platform navigates to about:blank can
 // hang forever; race every read so one stuck body cannot kill the 60s program.
 pending.push(Promise.race([(async()=>{
  try {
   if (r.status()===429) {apiError='platform_rate_limited';return;}
   if (r.status()===403) {apiError='access_denied';return;}
   const body=await r.json();
   const list=CFG.platform==='boss'?body?.zpData?.jobList:body?.data?.data?.jobCardList;
   if (!Array.isArray(list)) {apiError='needs_inspection';return;}
   for(const raw of list.slice(0,100)) {
    const j=CFG.platform==='boss'?mapBoss(raw):mapLiepin(raw);
    if(j.title&&j.company) records.push({...j,platform:CFG.platform,source_url:CFG.url,captured_at:new Date().toISOString()});
   }
  } catch(e) {apiError='needs_inspection';}
 })(),new Promise(res=>setTimeout(()=>res('body-timeout'),6000))]));
};
const bounded=(pr,ms)=>Promise.race([pr.catch(()=>null),new Promise(res=>setTimeout(()=>res(null),ms))]);
p.on('response',listener);
try {
 await p.goto(CFG.url,{waitUntil:'domcontentloaded',timeout:25000});
 // Bounded wait; no request replays, reload loops, fingerprint changes or bypass.
 // Every in-page read is raced: evaluates can hang while the platform navigates
 // the page to about:blank, and one hang would hit the 60s program deadline.
 const deadline=Date.now()+12000;
 for(let i=0;i<40 && !records.length && !apiError && Date.now()<deadline;i++) {
  const s=await bounded(p.evaluate(readState),3000);
  if(s?.blocked||s?.wall||p.url()==='about:blank') break;
  await p.waitForTimeout(250);
 }
 await Promise.race([Promise.all(pending),new Promise(res=>setTimeout(res,6000))]);
 let state=await bounded(p.evaluate(readState),3000)||{blocked:false,wall:false,empty:false};
 pagesRead=1;
 // Only an observed enabled next-page control can trigger another page.
 while(pagesRead<CFG.budget && records.length && !state.blocked && !state.wall && !apiError && p.url()!=='about:blank') {
  const next=p.getByRole('button',{name:'下一页',exact:true});
  if(await next.count()!==1 || !await next.isVisible() || !await next.isEnabled()) break;
  const before=records.length;
  await p.waitForTimeout(1200);
  await next.click({timeout:3000});
  pagesRead++;
  for(let i=0;i<16 && records.length===before&&!apiError;i++) await p.waitForTimeout(250);
  await Promise.race([Promise.all(pending),new Promise(res=>setTimeout(res,6000))]);
  state=await bounded(p.evaluate(readState),3000)||{blocked:false,wall:false};
  if(records.length===before) break;
 }
 const blanked=p.url()==='about:blank';
 let status=state.blocked?'blocked':apiError||(state.wall?'login_required':records.length?'ok':state.empty?'empty':blanked?'browser_error':'needs_inspection');
 preservePage=status==='login_required'||status==='blocked';
 if(status==='blocked') reportIssue('SITE_ACCESS_BLOCKED');
 if(status==='login_required') reportIssue('AUTHENTICATION_REQUIRED');
 // Listings already delivered by the platform's own API stay valid evidence after
 // the page is blanked; only login/captcha/rate-limit walls make them inaccessible.
 const inaccessible=status==='login_required'||status==='blocked'||status==='platform_rate_limited'||status==='access_denied';
 return {status,jobs:inaccessible?[]:records,pages:pagesRead,url:CFG.url,login:state.login||'unknown',
  ...(blanked?{blanked:true,immediate:!records.length}:{})};
} catch(e) {
 // Transport failures (including goto aborted by instant blanking) still return
 // whatever real evidence arrived before the failure.
 let blanked=false; try{blanked=p.url()==='about:blank';}catch(_){}
 const inaccessible=preservePage||apiError==='platform_rate_limited'||apiError==='access_denied';
 return {status:'browser_error',jobs:inaccessible?[]:records,pages:pagesRead,url:CFG.url,
  error:String(e?.message||e).slice(0,240),
  ...(blanked?{blanked:true,immediate:!records.length}:{})};
}
finally {
 try {p.off('response',listener);}catch(_){}
 // Always clean up our scratch page, including navigation failures. Genuine user
 // tabs and pages with an observed login/verification wall stay open.
 if(!reused && !preservePage) await p.close().catch(()=>{});
}
