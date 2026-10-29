import {parseTranscript} from './transcript.js';
import {registerPanadanWebMcp} from './webmcp.js';
import {callTypeLabel, callStateLabel, knownTypeOptions, knownStateOptions} from './labels.js';
'use strict';
const $ = id => document.getElementById(id);
let offset=0;
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
  for(const key of ['after','before','state','call_type','created_after','created_before'])if($(key)?.value)values.set(key,$(key).value);
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
        else if(key==='possibility_of_sale_ai')td.textContent=numberFormat(item[key]);
        else td.textContent=value;
        tr.append(td);
      }
      const td=el('td');const button=el('button','view-btn','مشاهده');
      button.type='button';button.setAttribute('aria-label','مشاهده جزئیات تماس '+safe(item.id));
      button.onclick=()=>detail(item.id);td.append(button);tr.append(td);$('rows').append(tr);
    }
    if(!data.items.length){const tr=el('tr'),td=el('td','muted','موردی پیدا نشد');td.colSpan=6;tr.append(td);$('rows').append(tr)}
  }catch(error){showError(error)}
}
async function metrics(){
  if(!$('metric-total'))return;
  try{
    const params=new URLSearchParams();
    for(const key of ['after','before','created_after','created_before'])if($(key)?.value)params.set(key,$(key).value);
    const data=await fetchJSON('/dashboard/metrics?'+params);
    $('metric-total').textContent=numberFormat(data.total);
    $('metric-sold').textContent=numberFormat(data.sold_out);
    $('metric-score').textContent=numberFormat(data.avg_ai_score);
    $('metric-length').textContent=numberFormat(data.avg_voice_length);
  }catch(error){showError(error)}
}
async function loadFilterOptions(){
  const makeOptions=(id,values,translate)=>{
    const select=$(id);if(!select)return;
    const current=select.value;
    const placeholder=select.options[0]?.textContent || 'همه';
    select.replaceChildren();
    const initial=document.createElement('option');initial.value='';initial.textContent=placeholder;select.append(initial);
    for(const raw of [...new Set(values.filter(v=>v!==null && v!==undefined && String(v).trim()).map(String))]){
      const option=document.createElement('option');option.value=raw;option.textContent=translate(raw);
      option.title=raw;select.append(option);
    }
    select.value=current;
  };
  // Static fallback works even if distinct-value lookup is unavailable.
  let types=knownTypeOptions(),states=knownStateOptions();
  try{
    const found=await fetchJSON('/dashboard/filter-options');
    if(Array.isArray(found.call_types))types=[...new Set([...types,...found.call_types])];
    if(Array.isArray(found.states))states=[...new Set([...states,...found.states])];
  }catch{
    // Filters remain functional with common known values.
  }
  makeOptions('call_type',types,callTypeLabel);
  makeOptions('state',states,callStateLabel);
}
const labels={id:'شناسه تماس',CALLDATE:'تاریخ تماس',call_id:'شناسه سیستمی',tellstate:'نوع تماس',tellside:'جهت تماس',aicallinfostate:'وضعیت AI',voice_length:'مدت صوت',possibility_of_sale_ai:'امتیاز AI',deal_value:'ارزش معامله',vw_danix_base_info_users_name:'کارشناس',customername:'نام مشتری',customertell:'شماره مشتری',outcome:'نتیجه تماس',ai_recommendation:'پیشنهاد AI',summary:'خلاصه',transcription:'متن مکالمه',tell_state_desc:'دلیل دسته‌بندی',create_date:'زمان ثبت'};
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
const heroFields=new Set(['id','CALLDATE','tellstate','aicallinfostate','possibility_of_sale_ai','vw_danix_base_info_users_name']);
function longTextSection(key, value){
  const section=el('article','detail-analysis');
  section.append(el('h3','detail-section-title',labels[key]||key));
  const content=String(value);
  if(content.length>620){
    const preview=el('p','detail-analysis-text',content.slice(0,420)+'…');
    const expand=el('details','inline-expand');
    const label=el('summary','','خواندن متن کامل');
    const complete=el('p','detail-analysis-text',content);
    expand.append(label,complete);
    section.append(preview,expand);
    expand.addEventListener('toggle',()=>{preview.hidden=expand.open;});
  }else section.append(el('p','detail-analysis-text',content));
  return section;
}
function metaValue(key,value){
  if(key==='CALLDATE')return dateFormat(value);
  if(key==='tellstate')return callTypeLabel(value);
  if(key==='aicallinfostate')return callStateLabel(value);
  if(key==='possibility_of_sale_ai')return numberFormat(value);
  if(key==='create_date'&&window.PanadanDate)
    return PanadanDate.format(value,{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23',timeZone:'Asia/Tehran'});
  return typeof value==='object'?JSON.stringify(value):String(value);
}
function conversationSection(raw){
  const section=el('details','conversation-section');
  const summary=el('summary','conversation-opener');
  const title=el('span','conversation-opener-title','متن کامل مکالمه');
  const stats=el('span','conversation-opener-info',numberFormat(raw.length)+' نویسه · برای مشاهده باز کنید');
  const arrow=el('span','conversation-chevron','⌄');
  summary.append(title,stats,arrow);
  section.append(summary);
  let rendered=false;
  section.addEventListener('toggle',()=>{
    if(!section.open||rendered)return;
    rendered=true;
    section.append(transcriptPanel(raw));
  });
  return section;
}
async function detail(id){
  $('veil').hidden=false;
  const drawer=$('veil').querySelector('.drawer');
  if(drawer)drawer.scrollTop=0;
  $('detail-title').textContent='تماس '+numberFormat(id);
  $('detail').replaceChildren(el('p','muted','در حال بارگذاری جزئیات...'));
  try{
    const data=await fetchJSON('/dashboard/data/'+encodeURIComponent(id));
    if($('veil').hidden)return;
    $('detail').replaceChildren();
    const hero=el('section','detail-overview');
    hero.append(el('h3','detail-section-title','نمای کلی تماس'));
    const chips=el('div','detail-chips');
    for(const [key,text] of [
      ['CALLDATE',dateFormat(data.CALLDATE)],
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
    if(data.possibility_of_sale_ai!==undefined&&data.possibility_of_sale_ai!==null){
      const score=el('p','detail-score','امتیاز ثبت‌شده: '+numberFormat(data.possibility_of_sale_ai));
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
      !heroFields.has(key)&&!priorityFields.includes(key)&&key!=='transcription'&&val!==null&&val!==''&&val!==undefined
    );
    if(extra.length){
      const block=el('section','detail-section');
      block.append(el('h3','detail-section-heading','اطلاعات تکمیلی'));
      const grid=el('div','detail-meta-grid');
      for(const [key,val] of extra){
        const item=el('div','detail-item');
        item.append(el('strong','',labels[key]||key),el('div','detail-value',metaValue(key,val)));
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
  }catch(error){$('detail').textContent=error.message;}
}
function clearDates(){
  for(const key of ['after','before','state','call_type','created_after','created_before']){
    if($(key))$(key).value='';
    const component=$(key+'-doran');if(component){component.removeAttribute('value');component.value=null;}
  }
}
function initialize(){
  for(const key of ['after','before'])PanadanDate.attach(key);
  for(const key of ['created_after','created_before'])PanadanDate.attachDateTime(key);
  const form=$('filters');if(form)form.onsubmit=event=>{event.preventDefault();offset=0;load();metrics()};
  if($('reset'))$('reset').onclick=()=>{clearDates();offset=0;load();metrics()};
  if($('refresh'))$('refresh').onclick=()=>{load();metrics()};
  if($('previous'))$('previous').onclick=()=>{offset=Math.max(0,offset-limit);load()};
  if($('next'))$('next').onclick=()=>{offset+=limit;load()};
  if($('close-drawer'))$('close-drawer').onclick=()=>{$('veil').hidden=true};
  if($('close-backdrop'))$('close-backdrop').onclick=()=>{$('veil').hidden=true};
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('veil'))$('veil').hidden=true});
  load();metrics();
  if($('call_type')||$('state'))loadFilterOptions();
  // WebMCP is an opt-in browser API; unsupported browsers behave normally.
  void registerPanadanWebMcp().then(result=>{
    const marker=$('webmcp-status');
    if(marker && result?.names?.length)marker.hidden=false;
  }).catch(()=>{ /* Experimental browser API does not affect the dashboard. */ });
}
initialize();
