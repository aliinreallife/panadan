import test from 'node:test';
import assert from 'node:assert/strict';
import {createWebMcpTools, registerPanadanWebMcp} from '../static/webmcp.js';

const find = (tools, name) => tools.find(t => t.name === name);

test('WebMCP is optional in unsupported browsers', async () => {
  const none=await registerPanadanWebMcp({page:{getElementById:()=>({})}});
  assert.equal(none,null);
  const zero=await registerPanadanWebMcp({page:{modelContext:{registerTool:()=>{}},getElementById:()=>null}});
  assert.equal(zero,null);
});

test('only permitted tools register and are marked read-only', async () => {
  const callsOnly=createWebMcpTools({canReadCalls:true,request:async()=>({})});
  const metricsOnly=createWebMcpTools({canReadMetrics:true,request:async()=>({})});
  assert.deepEqual(callsOnly.map(x=>x.name), ['panadan_find_calls','panadan_get_call_overview']);
  assert.deepEqual(metricsOnly.map(x=>x.name), ['panadan_get_call_metrics']);
  for (const tool of [...callsOnly,...metricsOnly]) {
    assert.equal(tool.annotations.readOnlyHint,true);
    assert.equal(tool.annotations.untrustedContentHint,true);
    assert.equal(tool.inputSchema.type,'object');
  }
});

test('call listing only returns approved metadata and preserves raw source keys', async () => {
  let url;
  const tools=createWebMcpTools({canReadCalls:true,request:async path=>{
    url=path;
    return {items:[{
      id:42, CALLDATE:'2026-10-29', tellstate:'FollowUp', aicallinfostate:'SoldOut',
      vw_danix_base_info_users_name:'Operator A', voice_length:90, possibility_of_sale_ai:80,
      summary:'PRIVATE SUMMARY', transcription:'PRIVATE TRANSCRIPT',
      customername:'Private Customer', customertell:'09121111111'
    }]};
  }});
  const result=await find(tools,'panadan_find_calls').execute({
    after:'2026-10-01',state:'SoldOut',limit:1
  });
  assert.match(url,/^\/dashboard\/data\?/);
  assert.match(url,/after=2026-10-01/);
  assert.match(url,/state=SoldOut/);
  assert.equal(result.items.length,1);
  assert.equal(result.items[0].type_fa,'پیگیری');
  assert.equal(result.items[0].state_fa,'فروش رفته');
  const serialized=JSON.stringify(result);
  assert.doesNotMatch(serialized,/PRIVATE|09121111111|customername|transcription|summary/);
});

test('overview uses the dedicated nonsensitive endpoint', async () => {
  const requests=[];
  const tools=createWebMcpTools({canReadCalls:true,request:async path=>{
    requests.push(path);
    return {id:7,CALLDATE:'2026-10-29',transcription:'DO NOT EXPOSE'};
  }});
  const result=await find(tools,'panadan_get_call_overview').execute({call_id:7});
  assert.deepEqual(requests,['/dashboard/overview/7']);
  assert.equal(result.id,7);
  assert.equal('transcription' in result,false);
});

test('input validation blocks arbitrary URLs, excessive pages, invalid dates', async () => {
  let count=0;
  const tools=createWebMcpTools({canReadCalls:true,canReadMetrics:true,request:async ()=>{
    count++;return {};
  }});
  const list=find(tools,'panadan_find_calls');
  for(const input of [
    {limit:21},{offset:-1},{limit:1.4},{state:'abc&danger=true'},
    {after:'2026-02-30'},{after:'2026-10-29',before:'2026-10-01'}
  ]) {
    assert.ok((await list.execute(input)).error);
  }
  assert.ok((await find(tools,'panadan_get_call_overview').execute({call_id:'7'})).error);
  assert.ok((await find(tools,'panadan_get_call_metrics').execute({after:'not-a-date'})).error);
  assert.equal(count,0);
});

test('browser tool requests use same-origin authenticated GET and abort on pagehide', async () => {
  const registrations=[],requests=[],listeners=[];
  const page={
    modelContext:{async registerTool(tool,opts){registrations.push({tool,opts});}},
    getElementById(id){return id==='rows' || id==='metric-total'?{}:null;},
    defaultView:{addEventListener(name,callback){listeners.push({name,callback});}}
  };
  const result=await registerPanadanWebMcp({
    page,
    fetchImpl:async (url,opts)=>{
      requests.push({url,opts});
      return {ok:true,json:async()=>({total:4})};
    }
  });
  assert.equal(result.names.length,3);
  assert.equal(registrations.length,3);
  const metrics=find(registrations.map(r=>r.tool),'panadan_get_call_metrics');
  assert.equal((await metrics.execute({})).total,4);
  assert.equal(requests[0].opts.method,'GET');
  assert.equal(requests[0].opts.credentials,'same-origin');
  assert.equal(requests[0].opts.cache,'no-store');
  assert.equal(requests[0].url,'/dashboard/metrics');
  assert.ok(listeners.some(x=>x.name==='pagehide'));
  listeners.find(x=>x.name==='pagehide').callback();
  assert.equal(result.controller.signal.aborted,true);
});

test('registration aborts and returns null when browser API rejects a tool', async () => {
  let signal;
  const result=await registerPanadanWebMcp({
    page:{modelContext:{async registerTool(_,options){signal=options.signal;throw Error('Experimental flag disabled')}},
      getElementById: id=>id==='rows'?{}:null}
  });
  assert.equal(result,null);
  assert.equal(signal.aborted,true);
});

test('WebMCP operator/team/destination filters preserve source values', async () => {
  const paths=[];
  const tools=createWebMcpTools({
    canReadCalls:true,canReadMetrics:true,
    request:async path=>{paths.push(path);return {items:[],total:0};}
  });
  await find(tools,'panadan_find_calls').execute({
    operator:'کارشناس مشهد',destination:'مشهد',team:'غرب آسیا',limit:5
  });
  const url=new URL('http://localhost'+paths[0]);
  assert.equal(url.searchParams.get('operator'),'کارشناس مشهد');
  assert.equal(url.searchParams.get('destination'),'مشهد');
  assert.equal(url.searchParams.get('team'),'غرب آسیا');
  await find(tools,'panadan_get_call_metrics').execute({operator:'کارشناس مشهد'});
  assert.equal(new URL('http://localhost'+paths[1]).searchParams.get('operator'),'کارشناس مشهد');
});
