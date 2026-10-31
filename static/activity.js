/* Panadan Activity — plain JS charts, no third-party telemetry or libraries. */
import {enhanceSelects} from './selects.js';
const $=id=>document.getElementById(id);
const formatNum=v=>new Intl.NumberFormat('fa-IR').format(Number(v||0));
const formatDay=day=>{
  try{return new Intl.DateTimeFormat('fa-IR-u-ca-persian',{month:'short',day:'numeric',timeZone:'UTC'})
    .format(new Date(day+'T12:00:00Z'));}catch{return day;}
};
// Event timestamps are Unix seconds (UTC). Convert once to Tehran local time;
// keep the original ISO instant for the native <time> element and auditability.
export function formatEventTimestamp(stamp) {
  if(stamp===null || stamp===undefined || stamp==='')return null;
  const seconds=Number(stamp);
  if(!Number.isFinite(seconds))return null;
  const instant=new Date(seconds*1000);
  if(!Number.isFinite(instant.valueOf()))return null;
  const locale='fa-IR-u-ca-persian', timeZone='Asia/Tehran';
  return {
    iso:instant.toISOString(),
    date:new Intl.DateTimeFormat(locale,{year:'numeric',month:'2-digit',day:'2-digit',timeZone}).format(instant),
    time:new Intl.DateTimeFormat(locale,{hour:'2-digit',minute:'2-digit',hourCycle:'h23',timeZone}).format(instant)
  };
}
const surfaceLabel={dashboard:'داشبورد',api:'REST API',mcp:'MCP',auth:'ورود و خروج'};
const actionTitles={
  'GET /dashboard':'باز کردن داشبورد',
  'GET /dashboard/data':'مرور فهرست تماس‌ها',
  'GET /dashboard/operator':'مشاهده صفحهٔ کارشناس',
  'GET /dashboard/operators':'فهرست کارشناسان و مقاصد',
  'POST /dashboard/operators/assign':'ثبت تیم یا مقصد کارشناس',
  'GET /dashboard/metrics':'مشاهده آمار تماس‌ها',
  'GET /dashboard/filter-options':'بارگذاری فیلترهای گزارش',
  'GET /dashboard/activity':'مشاهده فعالیت کاربران',
  'GET /dashboard/activity/data':'دریافت گزارش فعالیت',
  'GET /dashboard/overview/{id}':'مرور جزئیات تماس',
  'GET /dashboard/data/{id}':'مشاهده جزئیات مکالمه',
  'GET /dashboard/ai/transcript/{id}':'خواندن متن مکالمه برای AI',
  'GET /api/v1/calls':'API: فهرست تماس‌ها',
  'GET /api/v1/calls/{id}':'API: جزئیات تماس',
  'GET /api/v1/stats':'API: گزارش آماری',
  'GET /api/v1/states':'API: وضعیت‌ها',
  'MCP initialize':'شروع اتصال MCP',
  'MCP tools/list':'فهرست ابزارهای AI',
  'MCP tools/call:get_call_metrics':'MCP: مشاهده آمار تماس',
  'MCP tools/call:get_call_summary':'MCP: خلاصه تماس',
  'MCP tools/call:list_recent_calls':'MCP: فهرست تماس‌ها',
  'MCP tools/call:get_available_states':'MCP: وضعیت تماس‌ها',
  'MCP tools/call:get_redacted_call_transcript':'MCP: خواندن متن مکالمه',
  'POST /login:success':'ورود موفق کاربر',
  'POST /login:failed':'تلاش ناموفق برای ورود',
  'POST /logout':'خروج از حساب',
  'MCP unauthorized':'اتصال نامعتبر MCP'
};
export const actionLabel=name=>actionTitles[name] || name;

const node=(tag,cl,text)=>{
  const element=document.createElement(tag);
  if(cl)element.className=cl;
  if(text!==undefined)element.textContent=String(text);
  return element;
};
export const totals=report=>{
  const total=Number(report.total||0),errors=Number(report.errors||0);
  return {total,errors,users:Number(report.active_users ?? 0),
    success:total?Math.max(0,Math.round((total-errors)*100/total)):100};
};
export function completeDailySeries(rows, days, todayISO){
  const count=Math.max(1,Math.min(90,Number(days)||14));
  const today=new Date((todayISO || new Date().toISOString().slice(0,10))+'T00:00:00Z');
  if(Number.isNaN(today.valueOf()))return [];
  const keyed=new Map((rows||[]).map(row=>[row.day,row]));
  const result=[];
  for(let back=count-1;back>=0;back--){
    const date=new Date(today.valueOf()-back*86400000).toISOString().slice(0,10);
    const item=keyed.get(date);
    result.push({day:date,total:Number(item?.total||0),errors:Number(item?.errors||0)});
  }
  return result;
}
export function barScale(rows){
  const max=Math.max(1,...rows.map(row=>Number(row.total||0)));
  return rows.map(row=>({...row,pct:Math.round(Number(row.total||0)*100/max)}));
}
function renderBars(id,values,translate=x=>x){
  const target=$(id);target.replaceChildren();
  if(!values?.length){target.append(node('p','muted','برای این بازه فعالیتی ثبت نشده است.'));return;}
  for(const row of barScale(values)){
    const item=node('div','activity-bar-item');
    const title=node('div','activity-bar-title');
    title.append(node('span','activity-bar-name',translate(row.name)),
      node('strong','activity-bar-value',formatNum(row.total)));
    const track=node('div','activity-bar-track');
    const fill=node('span','activity-bar-fill');
    fill.style.width=row.pct+'%';track.append(fill);
    item.append(title,track);target.append(item);
  }
}
function renderTrend(values){
  const target=$('activity-trend');target.replaceChildren();
  if(!values?.length){target.append(node('p','muted','داده‌ای برای نمایش نمودار وجود ندارد.'));return;}
  const ordered=[...values].sort((a,b)=>a.day.localeCompare(b.day));
  const width=760,height=220,left=36,right=12,top=16,bottom=40;
  const yBase=height-bottom, graphWidth=width-left-right,graphHeight=yBase-top;
  const topY=Math.max(1,...ordered.map(x=>Number(x.total||0)));
  const xAt=i=>left+(ordered.length===1?graphWidth/2:i*graphWidth/(ordered.length-1));
  const yAt=v=>yBase-Number(v||0)/topY*graphHeight;
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('viewBox',`0 0 ${width} ${height}`);
  svg.setAttribute('role','img');
  svg.setAttribute('aria-label','فعالیت روزانه؛ منحنی سبز درخواست‌ها و نقاط قرمز خطاها');
  svg.classList.add('activity-svg');
  const svgNode=(name,attrs)=>{
    const el=document.createElementNS('http://www.w3.org/2000/svg',name);
    for(const [key,value] of Object.entries(attrs))el.setAttribute(key,String(value));
    return el;
  };
  for(let n=0;n<4;n++){
    const v=topY*n/3,y=yAt(v);
    svg.append(svgNode('line',{x1:left,x2:width-right,y1:y,y2:y,class:'activity-gridline'}));
    const label=svgNode('text',{x:0,y:y+4,class:'activity-y-label'});
    label.textContent=formatNum(Math.round(v));svg.append(label);
  }
  const points=ordered.map((v,i)=>[xAt(i),yAt(v.total)]);
  const linePoints=points.map(p=>p.join(',')).join(' ');
  const fillPoints=`${left},${yBase} ${linePoints} ${xAt(ordered.length-1)},${yBase}`;
  svg.append(svgNode('polygon',{points:fillPoints,class:'activity-area'}));
  svg.append(svgNode('polyline',{points:linePoints,class:'activity-line'}));
  const tickStep=Math.max(1,Math.ceil(ordered.length/6));
  ordered.forEach((v,i)=>{
    if(i%tickStep===0||i===ordered.length-1){
      const text=svgNode('text',{x:xAt(i),y:height-12,class:'activity-x-label','text-anchor':'middle'});
      text.textContent=formatDay(v.day);svg.append(text);
    }
    const point=svgNode('circle',{cx:xAt(i),cy:yAt(v.total),r:3,class:'activity-data-point'});
    const tooltip=svgNode('title',{});
    tooltip.textContent=`${formatDay(v.day)}: ${formatNum(v.total)} درخواست، ${formatNum(v.errors)} خطا`;
    point.append(tooltip);svg.append(point);
    if(Number(v.errors)>0){
      const error=svgNode('circle',{cx:xAt(i),cy:yAt(v.errors),r:3,class:'activity-error-point'});
      const et=svgNode('title',{});
      et.textContent=`${formatNum(v.errors)} خطا`;error.append(et);svg.append(error);
    }
  });
  target.append(svg);
}
let allRecent=[];
function renderEvents(items){
  const tbody=$('activity-events');tbody.replaceChildren();
  if(!items.length){const row=node('tr');const cell=node('td','muted','فعالیتی ثبت نشده است.');cell.colSpan=6;row.append(cell);tbody.append(row);return;}
  for(const event of items){
    const tr=node('tr');
    tr.title=event.action;
    const cell=node('td','activity-event-when');
    const stamp=formatEventTimestamp(event.created_at);
    if(stamp){
      const time=node('time','activity-time datetime-inline');
      time.dateTime=stamp.iso;
      time.title='زمان تهران';
      // RTL flex: first child is on the right. Clock before date.
      time.append(node('span','activity-clock datetime-clock',stamp.time),
        node('span','activity-date datetime-date',stamp.date));
      cell.append(time);
    }else cell.textContent='—';
    tr.append(cell);
    tr.append(node('td','activity-event-username',event.username??'—'));
    tr.append(node('td','',surfaceLabel[event.surface]||event.surface||'—'));
    tr.append(node('td','',actionLabel(event.action)||'—'));
    const status=node('td');
    const badge=node('span',Number(event.http_status)>=400?'activity-status failed':'activity-status successful',
      event.http_status);
    status.append(badge);tr.append(status);
    const duration=Number(event.duration_ms);
    const elapsed=Number.isFinite(duration)&&event.duration_ms!=null&&duration>=0
      ? formatNum(Math.round(duration))+' ms':'—';
    tr.append(node('td','activity-event-duration',elapsed));
    tbody.append(tr);
  }
}
function filterEvents(){
  const q=$('activity-search').value.trim().toLocaleLowerCase('fa');
  const matches=q?allRecent.filter(event=>
    [event.username,event.surface,surfaceLabel[event.surface],event.action,
     actionLabel(event.action),event.http_status].some(value=>
      String(value??'').toLocaleLowerCase('fa').includes(q))
  ):allRecent;
  renderEvents(matches);
  $('activity-event-count').textContent=formatNum(matches.length)+' از '+formatNum(allRecent.length)+' رویداد اخیر';
}
async function load(){
  $('activity-error').hidden=true;
  const params=new URLSearchParams({days:$('activity-days').value});
  if($('activity-user').value)params.set('user_id',$('activity-user').value);
  if($('activity-surface').value)params.set('surface',$('activity-surface').value);
  if($('activity-errors-only').checked)params.set('errors_only','true');
  try{
    const response=await fetch('/dashboard/activity/data?'+params,{credentials:'same-origin',cache:'no-store'});
    if(!response.ok)throw Error('unauthorized');
    const report=await response.json();
    const kpi=totals(report);
    $('activity-total').textContent=formatNum(kpi.total);
    $('activity-failed').textContent=formatNum(kpi.errors);
    $('activity-users').textContent=formatNum(kpi.users);
    $('activity-success').textContent=formatNum(kpi.success)+'٪';
    renderTrend(completeDailySeries(report.days,Number($('activity-days').value)));
    renderBars('activity-surfaces',report.surfaces,name=>surfaceLabel[name]||name);
    renderBars('activity-top-users',report.users);
    renderBars('activity-top-actions',report.actions,actionLabel);
    allRecent=report.recent||[];
    filterEvents();
    // The table searches the most recent events only, not the full database.
  }catch{
    $('activity-error').textContent='دریافت گزارش فعالیت ممکن نبود. لطفاً دسترسی مدیر و اتصال سرور را بررسی کنید.';
    $('activity-error').hidden=false;
  }
}
if(typeof document!=='undefined'){
  enhanceSelects();
  $('activity-filters')?.addEventListener('submit',e=>{e.preventDefault();void load();});
  $('activity-search')?.addEventListener('input',filterEvents);
  void load();
}
