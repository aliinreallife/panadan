import test from 'node:test';
import assert from 'node:assert/strict';
import {totals,barScale,completeDailySeries,actionLabel} from '../static/activity.js';

test('activity KPIs reflect all active accounts, not only chart top-users',()=>{
  const result=totals({total:200,errors:12,active_users:27,users:[{name:'A',total:50}]});
  assert.deepEqual(result,{total:200,errors:12,users:27,success:94});
});
test('chart bars use zero-safe maximum and preserve data',()=>{
  assert.deepEqual(barScale([{name:'A',total:10},{name:'B',total:5}]).map(x=>x.pct),[100,50]);
  assert.equal(barScale([{name:'A',total:0}])[0].pct,0);
});
test('friendly Persian labels preserve raw technical keys',()=>{
  assert.equal(actionLabel('MCP tools/call:get_redacted_call_transcript'),'MCP: خواندن متن مکالمه');
  assert.equal(actionLabel('GET /dashboard/activity'),'مشاهده فعالیت کاربران');
  assert.equal(actionLabel('unexpected future endpoint'),'unexpected future endpoint');
});

test('line chart includes quiet days and preserves UTC ordering',()=>{
  const days=completeDailySeries([{day:'2026-10-27',total:5,errors:1}],3,'2026-10-29');
  assert.deepEqual(days.map(x=>x.day),['2026-10-27','2026-10-28','2026-10-29']);
  assert.deepEqual(days.map(x=>x.total),[5,0,0]);
});
