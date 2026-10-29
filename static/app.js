import {parseTranscript} from './transcript.js';
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
  for(const key of ['after','before','state','created_after','created_before'])if($(key)?.value)values.set(key,$(key).value);
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
        if(key==='aicallinfostate'){const badge=el('span','status-badge',value);badge.dataset.status=value;td.append(badge)}
        else if(key==='CALLDATE')td.textContent=dateFormat(value);
        else if(key==='possibility_of_sale_ai')td.textContent=numberFormat(item[key]);
        else td.textContent=value;
        tr.append(td);
      }
      const td=el('td');const button=el('button','view-btn','جزئیات');button.onclick=()=>detail(item.id);td.append(button);tr.append(td);$('rows').append(tr);
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
async function detail(id){
  $('veil').hidden=false;$('detail-title').textContent='تماس '+numberFormat(id);
  $('detail').replaceChildren(el('p','muted','در حال بارگذاری...'));
  try{
    const data=await fetchJSON('/dashboard/data/'+id);$('detail').replaceChildren();
    if(typeof data.transcription==='string' && data.transcription.trim()){
      $('detail').append(transcriptPanel(data.transcription));
    }
    for(const [key,val] of Object.entries(data)){
      if(key==='transcription' || val===null || val==='')continue;
      const wrapper=el('div','detail-item');const heading=el('strong','',labels[key]||key);
      const text=key==='CALLDATE'?dateFormat(val):key==='create_date' && window.PanadanDate?PanadanDate.format(val,{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23',timeZone:'Asia/Tehran'}):typeof val==='object'?JSON.stringify(val):val;
      const value=el('div','',text);wrapper.append(heading,value);$('detail').append(wrapper);
    }
  }catch(error){$('detail').textContent=error.message}
}
function clearDates(){
  for(const key of ['after','before','state','created_after','created_before']){
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
}
initialize();
