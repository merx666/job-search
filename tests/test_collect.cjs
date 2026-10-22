const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
const src=fs.readFileSync('assets/collect.js','utf8');
async function run(platform,{body,wall=false,blocked=false,url='https://example.test',responseStatus=200,fireResponse=true,blankAfterResponse=false,reuse=false,gotoError=false,issueError=false}={}) {
 let listener,closed=false,newPages=0,current=url;
 const page={
  on:(name,fn)=>listener=fn,off:()=>{},
  goto:async()=>{
   if(fireResponse) listener({url:()=>platform==='boss'?'https://www.zhipin.com/wapi/zpgeek/search/joblist.json':'https://api-c.liepin.com/pc-search-job',status:()=>responseStatus,json:async()=>body});
   if(blankAfterResponse||!fireResponse) current='about:blank';
   if(gotoError) {await Promise.resolve();throw Error('synthetic navigation failure');}
  },
  evaluate:async()=>({wall,blocked,empty:false,login:'unknown'}),
  url:()=>current,waitForTimeout:async()=>{},close:async()=>{closed=true;},
  getByRole:()=>({count:async()=>0})
 };
 const result=await new AsyncFunction('CFG','readState','context','reportIssue','page',src)({platform,url,budget:3,reuse},()=>{}, {newPage:async()=>{newPages++;return page;}},()=>{if(issueError) throw Error('synthetic issue reporting failure');},page);
 return {result,closed,newPages};
}
test('boss maps explicit fields and retains source evidence',async()=>{
 const {result,closed}=await run('boss',{body:{zpData:{jobList:[{encryptJobId:'1',jobName:'电工',brandName:'样本企业',salaryDesc:'8-12K',cityName:'苏州',bossOnline:true,publishTime:'今天'}]}}});
 assert.equal(result.status,'ok');assert.equal(result.jobs[0].hr_active,'在线');assert.equal(result.jobs[0].publish_time,'今天');assert.ok(result.jobs[0].evidence);assert.equal(closed,true);assert.equal(result.pages,1);
});
test('liepin refresh never masquerades as publish',async()=>{
 const {result}=await run('liepin',{body:{data:{data:{jobCardList:[{job:{jobId:1,title:'会计',salary:'10-15k',dq:'上海-浦东',refreshTime:'今天'},comp:{compName:'样本公司'}}]}}}});
 assert.equal(result.jobs[0].refresh_time,'今天');assert.equal(result.jobs[0].publish_time,'');assert.equal(result.jobs[0].city,'上海');
});
test('login wall preserves page and exports no inaccessible records',async()=>{
 const {result,closed}=await run('boss',{wall:true,body:{zpData:{jobList:[{jobName:'会计',brandName:'样本公司'}]}}});
 assert.equal(result.status,'login_required');assert.deepEqual(result.jobs,[]);assert.equal(closed,false);
});
test('rate limits stop collection and the scratch page is cleaned up',async()=>{
 const {result,closed}=await run('boss',{responseStatus:429});assert.equal(result.status,'platform_rate_limited');assert.equal(closed,true);
});

test('blanking before any response is an immediate blank without records',async()=>{
 const {result}=await run('boss',{fireResponse:false});
 assert.equal(result.status,'browser_error');assert.deepEqual(result.jobs,[]);
 assert.equal(result.blanked,true);assert.equal(result.immediate,true);
});
test('blanking after capture keeps the already-delivered evidence',async()=>{
 const {result,closed}=await run('liepin',{blankAfterResponse:true,body:{data:{data:{jobCardList:[{job:{jobId:1,title:'会计',salary:'10-15k',dq:'上海-浦东'},comp:{compName:'样本公司'}}]}}}});
 assert.equal(result.status,'ok');assert.equal(result.jobs.length,1);
 assert.equal(result.blanked,true);assert.equal(result.immediate,false);assert.equal(closed,true);
});

test('pre-opened tab is reused for collection and never closed',async()=>{
 const {result,closed,newPages}=await run('boss',{reuse:true,body:{zpData:{jobList:[{jobName:'会计',brandName:'样本公司'}]}}});
 assert.equal(result.status,'ok');assert.equal(newPages,0);assert.equal(closed,false);
});
test('pre-opened tab kept even when blanked after capture',async()=>{
 const {result,closed}=await run('boss',{reuse:true,blankAfterResponse:true,body:{zpData:{jobList:[{jobName:'会计',brandName:'样本公司'}]}}});
 assert.equal(result.status,'ok');assert.equal(result.blanked,true);assert.equal(closed,false);
});
test('scratch page closes after unexpected schema so no blank tab is left',async()=>{
 const {result,closed}=await run('boss',{body:{code:7}});
 assert.equal(result.status,'needs_inspection');assert.equal(closed,true);
});
test('without an existing tab a disposable page is used and closed',async()=>{
 const {result,closed,newPages}=await run('boss',{body:{zpData:{jobList:[{jobName:'会计',brandName:'样本公司'}]}}});
 assert.equal(result.status,'ok');assert.equal(newPages,1);assert.equal(closed,true);
});
test('403 is not automatically a login or captcha request',async()=>{
 const {result}=await run('boss',{responseStatus:403});assert.equal(result.status,'access_denied');
});

test('navigation abort after blanking retains captured evidence and closes scratch page',async()=>{
 const {result,closed}=await run('boss',{gotoError:true,blankAfterResponse:true,body:{zpData:{jobList:[{jobName:'会计',brandName:'样本公司'}]}}});
 assert.equal(result.status,'browser_error');assert.equal(result.jobs.length,1);
 assert.equal(result.blanked,true);assert.equal(result.immediate,false);
 assert.equal(result.error,'synthetic navigation failure');assert.equal(closed,true);
});

test('navigation abort before any response closes scratch page and keeps immediate blank state',async()=>{
 const {result,closed}=await run('boss',{gotoError:true,fireResponse:false});
 assert.equal(result.status,'browser_error');assert.deepEqual(result.jobs,[]);
 assert.equal(result.blanked,true);assert.equal(result.immediate,true);assert.equal(closed,true);
 assert.equal(result.error,'synthetic navigation failure');
});

test('navigation abort on reused user tab preserves evidence without closing it',async()=>{
 const {result,closed,newPages}=await run('boss',{reuse:true,gotoError:true,blankAfterResponse:true,body:{zpData:{jobList:[{jobName:'会计',brandName:'样本公司'}]}}});
 assert.equal(result.jobs.length,1);assert.equal(result.blanked,true);assert.equal(result.immediate,false);
 assert.equal(result.error,'synthetic navigation failure');assert.equal(closed,false);assert.equal(newPages,0);
});

test('navigation abort without blanking still retains evidence and cleans up scratch page',async()=>{
 const {result,closed}=await run('boss',{gotoError:true,body:{zpData:{jobList:[{jobName:'会计',brandName:'样本公司'}]}}});
 assert.equal(result.status,'browser_error');assert.equal(result.jobs.length,1);
 assert.equal(result.blanked,undefined);assert.equal(result.error,'synthetic navigation failure');assert.equal(closed,true);
});

test('verification page stays open without exporting inaccessible records',async()=>{
 const {result,closed}=await run('boss',{blocked:true,body:{zpData:{jobList:[{jobName:'会计',brandName:'样本公司'}]}}});
 assert.equal(result.status,'blocked');assert.deepEqual(result.jobs,[]);assert.equal(closed,false);
});

test('issue reporting errors preserve login and verification pages without exporting records',async()=>{
 for(const blocked of [false,true]) {
  const {result,closed}=await run('boss',{wall:!blocked,blocked,issueError:true,body:{zpData:{jobList:[{jobName:'会计',brandName:'样本公司'}]}}});
  assert.equal(result.status,'browser_error');assert.deepEqual(result.jobs,[]);
  assert.equal(result.error,'synthetic issue reporting failure');assert.equal(closed,false);
 }
});
