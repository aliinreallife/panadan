'use strict';
// mcp-apps.js controls canonical field eligibility. This layer mirrors shared
// fields, never creates additional named inputs or grants them automatically.
for(const form of document.querySelectorAll('.consent-accordion-form')){
 const caps=new Map([...form.querySelectorAll('input[name="capabilities"]')].map(x=>[x.value,x]));
 const fields=new Map([...form.querySelectorAll('input[name="fields"]')].map(x=>[x.value,x]));
 const groups=[...form.querySelectorAll('[data-consent-group]')];
 const mirrors=[...form.querySelectorAll('[data-shared-field]')];
 const status=form.querySelector('[data-consent-status]');
 const fmt=new Intl.NumberFormat('fa-IR');
 const call=caps.get('calls:read'),transcript=caps.get('calls:transcript:read');
 const sync=()=>{
   if(transcript && !call?.checked && transcript.checked){
     transcript.checked=false;
     transcript.dispatchEvent(new Event('change',{bubbles:true}));
   }
   for(const mirror of mirrors){
     const canonical=fields.get(mirror.dataset.sharedField);
     mirror.closest('[data-shared-row]').hidden=!canonical;
     mirror.disabled=!canonical||canonical.disabled||!caps.get('metrics:read')?.checked;
     mirror.checked=!!canonical?.checked;
   }
   for(const group of groups){
     const cap=caps.get(group.dataset.consentGroup);
     const controls=[...group.querySelectorAll('input[name="fields"],[data-shared-field]')];
     const selected=cap?.checked?controls.filter(x=>x.checked&&!x.disabled).length:0;
     group.querySelector('[data-group-count]').textContent=cap?.checked?fmt.format(selected)+' مورد انتخاب شده':cap?'غیرفعال':'غیرمجاز';
     group.classList.toggle('is-selected',!!cap?.checked);
   }
   if(status)status.textContent=fields.get('transcription')?.checked&&!fields.get('id')?.checked?
       'برای دریافت متن مکالمه، شناسه تماس را نیز در گزارش تماس‌ها انتخاب کنید.':'';
 };
 for(const mirror of mirrors)mirror.addEventListener('change',()=>{
   const canonical=fields.get(mirror.dataset.sharedField);
   if(canonical&&!canonical.disabled&&!mirror.disabled){
     canonical.checked=mirror.checked;
     canonical.dispatchEvent(new Event('change',{bubbles:true}));
   }
   sync();
 });
 for(const control of [...caps.values(),...fields.values()])control.addEventListener('change',sync);
 form.addEventListener('submit',event=>{
   if(fields.get('transcription')?.checked&&!fields.get('id')?.checked){
     event.preventDefault();
     const group=groups.find(x=>x.dataset.consentGroup==='calls:read');
     if(group)group.open=true;
     fields.get('id')?.focus();
     sync();
   }
 });
 sync();
}
