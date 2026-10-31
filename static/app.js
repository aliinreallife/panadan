import {parseTranscript} from './transcript.js';
import {enhanceSelects} from './selects.js';
import {enhanceMultiSelects, multiValues} from './multiselect.js';
import {registerPanadanWebMcp} from './webmcp.js';
import {formatVoiceDuration, voiceDurationSegments, formatSourceCallClock, hasDisplayableDealValue} from './formatters.js';
import {dialablePhone} from './phone.js';
import {callTypeLabel, callStateLabel, directionLabel, knownTypeOptions, knownStateOptions} from './labels.js';
'use strict';
const $ = id => document.getElementById(id);
let offset=0;
let detailRequestId=0;
let drawerReturnFocus=null;
const profileOperator=document.getElementById('dashboard-content')?.dataset.profileOperator||'';
const operatorName=value=>value==='__unspecified__'||!String(value||'').trim()?'نامشخص':String(value);
const limit=20;
const dateFormat = value => window.PanadanDate ? PanadanDate.format(value) : value;
const numberFormat = value => value === null || value === undefined ? '—' : new Intl.NumberFormat('fa-IR').format(value);
const fetchJSON = async url => {
  const res = await fetch(url,{credentials:'same-origin',cache:'no-store'});
  if(res.status===401){location.href='/login';throw Error('ابتدا وارد شوید')}
  if(res.status===403)throw Error('برای مشاهدهٔ این بخش مجوز ندارید');
  if(!res.ok)throw Error(`دریافت داده ناموفق بود (${res.status})`);
  return res.json();
};
const safe = value => value === null || value === undefined || value === '' ? '—' : String(value);
const el = (tag,cls,text) => {
  const element = document.createElement(tag);
  if(cls)element.className=cls;
  if(text!==undefined)element.textContent=safe(text);
  return element;
};
const showError=error=>{const target=$('error');if(target){target.textContent=error.message;target.hidden=false;}};
const clearError=()=>{if($('error'))$('error').hidden=true;};
const filters=()=>{
  const values=new URLSearchParams({limit,offset});
  for(const key of ['after','before'])if($(key)?.value)values.set(key,$(key).value);
  for(const [id,key] of [
    ['operator','operators'],['destination','destination'],
    ['team','team'],['call_type','call_type'],
    ['state','state'],['direction','direction']
  ]){
    const select=$(id);
    if(select)for(const value of multiValues(select))values.append(key,value);
  }
  // Operator profile identity is fixed independently from OR report facets.
  if(profileOperator)values.set('operator',profileOperator);
  return values;
};

async function load(){
  if(!$('rows'))return;
  clearError();
  const spinner=el('tr');const message=el('td','muted','در حال دریافت...');message.colSpan=6;spinner.append(message);$('rows').replaceChildren(spinner);
  try{
    const data=await fetchJSON('/dashboard/data?'+filters());
    $('rows').replaceChildren();
    $('count').textContent=numberFormat(data.items.length)+' مورد';
    $('page').textContent='صفحه '+numberFormat(Math.floor(offset/limit)+1);
    $('previous').disabled=offset===0;
    $('next').disabled=data.items.length<limit;
    for(const item of data.items){
      const tr=el('tr');
      for(const key of ['CALLDATE','vw_danix_base_info_users_name','tellstate','aicallinfostate','possibility_of_sale_ai']){
        const td=el('td');const value=safe(item[key]);
        td.dataset.label=({
          CALLDATE:'تاریخ',vw_danix_base_info_users_name:'کارشناس',
          tellstate:'نوع تماس',aicallinfostate:'وضعیت AI',
          possibility_of_sale_ai:'امتیاز AI'
        })[key]||key;
        if(key==='aicallinfostate'){
          const badge=el('span','status-badge',callStateLabel(item[key]));
          badge.dataset.status=safe(item[key]).replace(/[^\w]/g,'');
          badge.title='مقدار اصلی: '+value;
          td.append(badge);
        } else if(key==='tellstate'){
          const badge=el('span','type-badge',callTypeLabel(item[key]));
          badge.title='مقدار اصلی: '+value;
          td.append(badge);
        } else if(key==='CALLDATE')td.textContent=dateFormat(value);
        else if(key==='vw_danix_base_info_users_name'){
          const name=(value==='—'||!String(value).trim())?'__unspecified__':String(value);
          const link=el('a','operator-name-link',operatorName(name));
          link.href='/dashboard/operator?name='+encodeURIComponent(name);
          link.title='مشاهده آمار و تماس‌های '+operatorName(name);
          td.append(link);
        }
        else if(key==='possibility_of_sale_ai'){
          td.textContent=numberFormat(item[key]);
          td.title=item[key]===null||item[key]===undefined
            ? 'امتیاز AI برای این تماس ثبت نشده است.'
            : 'امتیاز تخمینی احتمال فروش از سامانه مبدأ؛ به معنی فروش قطعی یا احتمال تضمین‌شده نیست.';
        }
        else td.textContent=value;
        tr.append(td);
      }
      const td=el('td');td.dataset.label='جزئیات';const button=el('button','view-btn','مشاهده');
      button.type='button';button.setAttribute('aria-label','مشاهده جزئیات تماس '+safe(item.id));
      button.onclick=()=>detail(item.id);td.append(button);tr.append(td);$('rows').append(tr);
    }
    if(!data.items.length){const tr=el('tr'),td=el('td','muted','موردی پیدا نشد');td.colSpan=6;tr.append(td);$('rows').append(tr)}
  }catch(error){showError(error)}
}
async function metrics(){
  if(!$('metric-total'))return;
  try{
    const params=filters();
    params.delete('limit');
    params.delete('offset');
    const data=await fetchJSON('/dashboard/metrics?'+params);
    $('metric-total').textContent=numberFormat(data.total);
    $('metric-sold').textContent=numberFormat(data.sold_out);
    $('metric-score').textContent=numberFormat(data.avg_ai_score);
    const coverage=$('metric-score-coverage');
    if(coverage){
      const counted=data.scored_calls!==null&&data.scored_calls!==undefined;
      const totalKnown=data.total!==null&&data.total!==undefined;
      coverage.textContent=counted&&totalKnown
        ? numberFormat(data.scored_calls)+' از '+numberFormat(data.total)+' تماس دارای امتیاز'
        : 'میانگین صرفاً از تماس‌های دارای امتیاز';
    }
    const duration=$('metric-length');
    const units=voiceDurationSegments(data.avg_voice_length);
    duration.replaceChildren();
    if(!units.length)duration.textContent='—';
    for(const [i,unit] of units.entries()){
      if(i)duration.append(el('span','duration-join','و'));
      const part=el('bdi','duration-part',unit);
      part.dir='rtl';
      duration.append(part);
    }
    duration.setAttribute('aria-label',formatVoiceDuration(data.avg_voice_length));
  }catch(error){showError(error)}
}
async function loadFilterOptions(){
  const makeOptions=(id,values,translate)=>{
    const select=$(id);if(!select)return;
    const current=new Set(multiValues(select));
    select.replaceChildren();
    for(const raw of [...new Set(values.filter(v=>v!==null && v!==undefined && String(v).trim()).map(String))]){
      const option=document.createElement('option');
      option.value=raw;option.textContent=translate(raw);
      option.title=raw;option.selected=current.has(raw);
      select.append(option);
    }
    select.dispatchEvent(new Event('change',{bubbles:true}));
  };

  // Static fallback works even if distinct-value lookup is unavailable.
  let types=knownTypeOptions(),states=knownStateOptions();
  let foundOperators=[],foundDestinations=['نامشخص'],foundTeams=['نامشخص'],foundDirections=[];
  try{
    const found=await fetchJSON('/dashboard/filter-options');
    if(Array.isArray(found.call_types))types=[...new Set([...types,...found.call_types])];
    if(Array.isArray(found.states))states=[...new Set([...states,...found.states])];
    if(Array.isArray(found.operators))foundOperators=found.operators;
    if(Array.isArray(found.destinations))foundDestinations=found.destinations;
    if(Array.isArray(found.teams))foundTeams=found.teams;
    if(Array.isArray(found.directions))foundDirections=found.directions;
  }catch{
    // Filters remain functional with common known values.
  }
  makeOptions('call_type',types,callTypeLabel);
  makeOptions('state',states,callStateLabel);
  // Source owner confirmed IntoOut=outgoing, OutToIn=incoming.
  // Raw source codes remain option values for backend filtering.
  makeOptions('direction',foundDirections,directionLabel);
  const directory=Array.isArray(foundOperators)?foundOperators:[];
  makeOptions('operator',directory.map(v=>v.value),v=>operatorName(v));
  makeOptions('destination',foundDestinations,v=>v);
  makeOptions('team',foundTeams,v=>v);
}
const labels={id:'شناسه تماس',CALLDATE:'تاریخ تماس',call_id:'شناسه سیستمی',tellstate:'نوع تماس',tellside:'جهت تماس',aicallinfostate:'وضعیت AI',voice_length:'مدت صوت',possibility_of_sale_ai:'امتیاز احتمال فروش (AI)',deal_value:'ارزش معامله (تأییدنشده)',call_time:'ساعت تماس (طبق مبدأ)',vw_danix_base_info_users_name:'کارشناس',customername:'نام مشتری',customertell:'شماره مشتری',outcome:'نتیجه تماس',ai_recommendation:'پیشنهاد AI',summary:'خلاصه',transcription:'متن مکالمه',tell_state_desc:'دلیل دسته‌بندی',create_date:'زمان ثبت'};
function transcriptPanel(raw){
  const parsed=parseTranscript(raw);
  const panel=el('section','transcript-panel');
  const head=el('div','transcript-heading');
  const title=el('div','transcript-title');
  title.append(el('strong','', 'متن مکالمه'),el('span','transcript-label','نسخهٔ خوانای پانادان · Panadan'));
  const actions=el('div','transcript-actions');
  const formatted=el('button','transcript-tab active','نسخهٔ پانادان');
  const original=el('button','transcript-tab','متن خام (Raw)');
  formatted.type=original.type='button';
  const copy=el('button','secondary copy-transcript','کپی متن اصلی');copy.type='button';
  const display=el('div','transcript-content');
  const explanation=el('p','transcript-note','قالب‌بندی خودکار است؛ متن و ترتیب گفتار تغییر داده نشده و تشخیص گوینده ممکن است کامل نباشد.');
  const switchTo=(rawMode)=>{
    formatted.classList.toggle('active',!rawMode);
    original.classList.toggle('active',rawMode);
    formatted.setAttribute('aria-pressed', String(!rawMode));
    original.setAttribute('aria-pressed', String(rawMode));
    display.replaceChildren();
    if(rawMode){
      const rawNode=el('pre','transcript-raw');
      rawNode.textContent=parsed.raw;
      display.append(rawNode);
      return;
    }
    const note=el('div','transcript-info',`${numberFormat(parsed.turns.length)} بخش گفتگو`);
    display.append(note);
    if(parsed.warnings.length){const warning=el('p','transcript-warning',parsed.warnings.join(' · '));display.append(warning);}
    const turns=el('div','transcript-turns');
    const appendTurns=(max)=>{
      const frag=document.createDocumentFragment();
      for(const part of parsed.turns.slice(turns.children.length,max)){
        const isOperator=part.speaker==='اپراتور';
        const card=el('div','speech-turn '+(isOperator?'speech-operator':part.speaker==='مشتری'?'speech-customer':'speech-unknown'));
        card.append(el('span','speaker-tag',part.speaker),el('p','speech-body',part.text));
        frag.append(card);
      }
      turns.append(frag);
    };
    appendTurns(Math.min(80,parsed.turns.length));
    display.append(turns);
    if(parsed.turns.length>80){
      const more=el('button','secondary load-transcript','نمایش بخش‌های بیشتر');more.type='button';
      more.addEventListener('click',()=>{
        appendTurns(Math.min(turns.children.length+80,parsed.turns.length));
        if(turns.children.length===parsed.turns.length)more.remove();
      });
      display.append(more);
    }
  };
  formatted.onclick=()=>switchTo(false);original.onclick=()=>switchTo(true);
  copy.onclick=async()=>{
    try {await navigator.clipboard.writeText(parsed.raw);copy.textContent='کپی شد';}
    catch {copy.textContent='کپی خودکار در دسترس نیست';}
  };
  actions.append(formatted,original,copy);head.append(title,actions);
  panel.append(head,explanation,display);switchTo(false);
  return panel;
}
const priorityFields=['summary','outcome','ai_recommendation','tell_state_desc'];
const heroFields=new Set(['id','CALLDATE','tellstate','aicallinfostate','possibility_of_sale_ai','vw_danix_base_info_users_name','call_time']);
function longTextSection(key, value){
  const section=el('article','detail-analysis');
  const heading=el('h3','detail-section-title',labels[key]||key);
  section.append(heading);
  const content=String(value);
  if(content.length<=620){
    section.append(el('p','detail-analysis-text',content));
    return section;
  }
  const preview=el('p','detail-analysis-text',content.slice(0,360).trimEnd()+'…');
  const full=el('p','detail-analysis-text',content);
  const toggle=el('button','analysis-read-more');
  toggle.type='button';
  toggle.setAttribute('aria-expanded','false');
  const target='analysis-full-'+Math.random().toString(36).slice(2,10);
  full.id=target;toggle.setAttribute('aria-controls',target);
  full.hidden=true;
  const icon=el('span','analysis-toggle-icon','⌄');icon.setAttribute('aria-hidden','true');
  const caption=el('span','','نمایش متن کامل');
  toggle.append(caption,icon);
  toggle.addEventListener('click',()=>{
    const expanded=toggle.getAttribute('aria-expanded')!=='true';
    toggle.setAttribute('aria-expanded',String(expanded));
    preview.hidden=expanded;
    full.hidden=!expanded;
    caption.textContent=expanded?'بستن متن':'نمایش متن کامل';
  });
  section.append(preview,full,toggle);
  return section;
}

function metaValue(key,value){
  if(key==='CALLDATE')return dateFormat(value);
  if(key==='tellstate')return callTypeLabel(value);
  if(key==='aicallinfostate')return callStateLabel(value);
  if(key==='possibility_of_sale_ai')return numberFormat(value);
  if(key==='voice_length')return formatVoiceDuration(value);
  if(key==='call_time')return formatSourceCallClock(value);
  if(key==='deal_value')return numberFormat(value);

  return typeof value==='object'?JSON.stringify(value):String(value);
}
// Shared RTL time/date display: first child (clock) is rightmost; date is left.
function dateTimeNode({clock,day,zone='',className=''}) {
  const wrapper=el('span','datetime-inline'+(className?' '+className:''));
  wrapper.dir='rtl';
  const hour=el('bdi','datetime-clock',clock);
  const date=el('bdi','datetime-date',day);
  hour.dir=date.dir='ltr';
  wrapper.append(hour,date);
  if(zone)wrapper.append(el('span','datetime-zone',zone));
  return wrapper;
}
function recordedDateTime(value) {
  if(!window.PanadanDate)return el('span','',String(value));
  const opts={timeZone:'Asia/Tehran'};
  const day=PanadanDate.format(value,{year:'numeric',month:'2-digit',day:'2-digit',...opts});
  const clock=PanadanDate.format(value,{hour:'2-digit',minute:'2-digit',hourCycle:'h23',...opts});
  // Date/time are formatted independently so browser bidi reordering cannot
  // place the Persian date to the right of the time.
  const stamp=dateTimeNode({clock,day,className:'recorded-datetime'});
  stamp.title='تاریخ و ساعت ثبت به وقت تهران';
  return stamp;
}
function conversationSection(raw){
  const section=el('details','conversation-section');
  const summary=el('summary','conversation-opener');
  const icon=el('span','conversation-icon');
  icon.textContent='☷';
  icon.setAttribute('aria-hidden','true');
  const titleBlock=el('span','conversation-title-block');
  titleBlock.append(
    el('strong','conversation-opener-title','متن کامل مکالمه'),
    el('span','conversation-preview','نسخهٔ خوانا، تفکیک گوینده و متن اصلی')
  );
  const meta=el('span','conversation-opener-info',numberFormat(raw.length)+' نویسه');
  const toggle=el('span','conversation-toggle');
  const toggleText=el('span','conversation-toggle-label','باز کردن مکالمه');
  const arrow=el('span','conversation-chevron','⌄');
  arrow.setAttribute('aria-hidden','true');
  toggle.append(toggleText,arrow);
  summary.append(icon,titleBlock,meta,toggle);
  section.append(summary);
  let rendered=false;
  section.addEventListener('toggle',()=>{
    toggleText.textContent=section.open?'بستن مکالمه':'باز کردن مکالمه';
    if(!section.open||rendered)return;
    rendered=true;
    section.append(transcriptPanel(raw));
  });
  return section;
}

function closeDetail(){
  if($('veil')?.hidden)return;
  detailRequestId += 1;
  $('veil').hidden=true;
  document.body.classList.remove('drawer-open');
  $('detail')?.removeAttribute('aria-busy');
  if(drawerReturnFocus?.isConnected)drawerReturnFocus.focus();
  drawerReturnFocus=null;
}
async function detail(id){
  const requestId=++detailRequestId;
  if($('veil').hidden)drawerReturnFocus=document.activeElement;
  $('veil').hidden=false;
  document.body.classList.add('drawer-open');
  $('close-drawer').focus();
  const drawer=$('veil').querySelector('.drawer');
  if(drawer)drawer.scrollTop=0;
  $('detail-title').textContent='تماس '+numberFormat(id);
  const loading=el('p','muted','در حال دریافت جزئیات تماس...');
  loading.setAttribute('role','status');
  $('detail').setAttribute('aria-busy','true');
  $('detail').replaceChildren(loading);
  try{
    const data=await fetchJSON('/dashboard/data/'+encodeURIComponent(id));
    if($('veil').hidden || requestId!==detailRequestId)return;
    $('detail').replaceChildren();
    const hero=el('section','detail-overview');
    hero.append(el('h3','detail-section-title','نمای کلی تماس'));
    const chips=el('div','detail-chips');
    // One visual date/time group: clock on the RIGHT, date on the LEFT.
    // The source has not confirmed which call event the time denotes.
    const when=el('div','detail-chip detail-chip-datetime');
    when.append(el('span','detail-chip-label','تاریخ و ساعت تماس'));
    when.append(dateTimeNode({
      clock:formatSourceCallClock(data.call_time),
      day:dateFormat(data.CALLDATE),
      className:'call-datetime'
    }));
    when.append(el('span','detail-clock-hint','ساعت احتمالی به وقت تهران · رویداد تماس هنوز تأیید نشده'));
    when.title='ساعت استخراج‌شده از ثانیه‌های روز در سامانه مبدأ؛ زمان شروع یا پایان تماس تأیید نشده است.';
    chips.append(when);
    for(const [key,text] of [
      ['vw_danix_base_info_users_name',safe(data.vw_danix_base_info_users_name)],
      ['tellstate',callTypeLabel(data.tellstate)],
      ['aicallinfostate',callStateLabel(data.aicallinfostate)]
    ]){
      const chip=el('div','detail-chip');
      chip.append(el('span','detail-chip-label',labels[key]||key),el('strong','',text));
      if(key==='tellstate'||key==='aicallinfostate')chip.title='مقدار اصلی: '+safe(data[key]);
      chips.append(chip);
    }
    hero.append(chips);
    if(Object.hasOwn(data,'possibility_of_sale_ai')){
      const present=data.possibility_of_sale_ai!==null&&data.possibility_of_sale_ai!==undefined;
      const score=el('p','detail-score','امتیاز احتمال فروش (AI): '+(present?numberFormat(data.possibility_of_sale_ai):'ثبت نشده'));
      score.title='امتیاز تخمینی از سامانه مبدأ است؛ معادل احتمال قطعی یا فروش تأییدشده نیست.';
      hero.append(score);
    }
    $('detail').append(hero);
    const analyzed=priorityFields.filter(key=>data[key]!==null&&data[key]!==undefined&&String(data[key]).trim());
    if(analyzed.length){
      const block=el('section','detail-section');
      block.append(el('h3','detail-section-heading','خلاصه و تحلیل'));
      for(const key of analyzed)block.append(longTextSection(key,data[key]));
      $('detail').append(block);
    }
    const extra=Object.entries(data).filter(([key,val])=>
      !heroFields.has(key)&&!priorityFields.includes(key)&&key!=='transcription'&&val!==null&&val!==''&&val!==undefined&&
      (key!=='deal_value'||hasDisplayableDealValue(val))
    );
    if(extra.length){
      const block=el('section','detail-section');
      block.append(el('h3','detail-section-heading','اطلاعات تکمیلی'));
      const grid=el('div','detail-meta-grid');
      for(const [key,val] of extra){
        const item=el('div','detail-item');
        item.append(el('strong','',labels[key]||key));
        if(key==='customertell'){
          // Sensitive details only: the server omits this field for callers
          // without calls:sensitive. Never fall back to numeric tellnum.
          const value=el('div','detail-value customer-phone-row');
          const digits=el('bdi','customer-phone-number',String(val));
          digits.dir='ltr';
          value.append(digits);
          const dialHref=dialablePhone(val);
          if(dialHref){
            const call=el('a','call-link','تماس');
            call.href=dialHref;
            call.title='باز کردن شماره‌گیر دستگاه';
            call.setAttribute('aria-label','تماس با شماره '+String(val));
            value.append(call);
          }
          item.append(value);
        }else if(key==='create_date'){
          const value=el('div','detail-value');
          value.append(recordedDateTime(val));
          item.append(value);
        }else{
          item.append(el('div','detail-value',metaValue(key,val)));
        }
        if(key==='deal_value'){
          item.title='مقدار مستقیم از سامانه مبدأ؛ معنای عدد، واحد پول و تأیید مالی آن هنوز مشخص نیست.';
          item.append(el('span','form-hint','واحد پول و تأیید مالی این مقدار از مبدأ مشخص نیست.'));
        }
        grid.append(item);
      }
      block.append(grid);$('detail').append(block);
    }
    if(typeof data.transcription==='string'&&data.transcription.trim()){
      const end=el('section','detail-section transcript-last');
      end.append(el('h3','detail-section-heading','مکالمه'));
      end.append(conversationSection(data.transcription));
      $('detail').append(end);
    }
  }catch(error){
    if(requestId===detailRequestId && !$('veil').hidden){
      $('detail').replaceChildren(el('p','error','دریافت جزئیات ممکن نشد. دوباره تلاش کنید.'));
    }
  }finally{
    if(requestId===detailRequestId)$('detail')?.removeAttribute('aria-busy');
  }
}
function clearDates(){
  for(const key of ['after','before','state','call_type','operator','destination','team','direction']){
    if($(key)){
      if($(key).multiple){for(const option of $(key).options)option.selected=false;$(key).dispatchEvent(new Event('change',{bubbles:true}));}
      else $(key).value='';
    }
    const component=$(key+'-doran');if(component){component.removeAttribute('value');component.value=null;}
  }
}
function initialize(){
  enhanceSelects();
  enhanceMultiSelects();
  for(const key of ['after','before'])PanadanDate.attach(key);
  // The optional creation-time controls are removed from the dashboard.
  // Legacy created_after/created_before API support stays server-side.
  const form=$('filters');if(form)form.onsubmit=event=>{event.preventDefault();offset=0;load();metrics()};
  if($('reset'))$('reset').onclick=()=>{clearDates();offset=0;load();metrics()};
  if($('refresh'))$('refresh').onclick=()=>{load();metrics()};
  if($('previous'))$('previous').onclick=()=>{offset=Math.max(0,offset-limit);load()};
  if($('next'))$('next').onclick=()=>{offset+=limit;load()};
  if($('close-drawer'))$('close-drawer').onclick=closeDetail;
  if($('close-backdrop'))$('close-backdrop').onclick=closeDetail;
  document.addEventListener('keydown',e=>{
    if($('veil')?.hidden)return;
    if(e.key==='Escape'){e.preventDefault();closeDetail();return;}
    if(e.key!=='Tab')return;
    const drawer=$('veil').querySelector('.drawer');
    const options=[...drawer.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,[tabindex]:not([tabindex="-1"])')]
      .filter(node=>node.getClientRects().length && !node.closest('[hidden]'));
    if(!options.length){e.preventDefault();drawer.focus();return;}
    const first=options[0],last=options[options.length-1];
    if(e.shiftKey && (document.activeElement===first || !drawer.contains(document.activeElement))){e.preventDefault();last.focus();}
    else if(!e.shiftKey && (document.activeElement===last || !drawer.contains(document.activeElement))){e.preventDefault();first.focus();}
  });
  load();metrics();
  if($('call_type')||$('state'))loadFilterOptions();
  // WebMCP is an opt-in browser API; unsupported browsers behave normally.
  void registerPanadanWebMcp().then(result=>{
    const marker=$('webmcp-status');
    if(marker && result?.names?.length)marker.hidden=false;
  }).catch(()=>{ /* Experimental browser API does not affect the dashboard. */ });
}
initialize();
