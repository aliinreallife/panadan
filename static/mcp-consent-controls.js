'use strict';
// Explicit user actions only. Never auto-grant columns on page load.
for (const form of document.querySelectorAll('.mcp-consent-form')) {
  const tools=form.querySelector('[data-selection-tools]');
  const count=form.querySelector('[data-selection-count]');
  const select=form.querySelector('[data-select-eligible]');
  const clear=form.querySelector('[data-clear-fields]');
  if(!tools||!count||!select||!clear) continue;
  const fields=Array.from(form.querySelectorAll('input[name="fields"]'));
  const caps=Array.from(form.querySelectorAll('input[name="capabilities"]'));
  const fmt=new Intl.NumberFormat('fa-IR');
  const toolbar=form.querySelector('[data-consent-toolbar]');
  const standard=form.querySelector('[data-standard-access]');
  const summary=form.querySelector('[data-field-summary]');
  const sync=()=>{
    const enabled=fields.filter(x=>!x.disabled);
    count.textContent=fmt.format(enabled.filter(x=>x.checked).length)+' از '+fmt.format(enabled.length)+' ستون مجاز انتخاب شده';
    if(summary)summary.textContent=fmt.format(enabled.filter(x=>x.checked).length)+' ستون انتخاب شده';
    select.disabled=!enabled.some(x=>!x.checked);
    clear.disabled=!enabled.some(x=>x.checked);
  };
  select.addEventListener('click',()=>{
    for(const field of fields) if(!field.disabled) field.checked=true;
    sync();
  });
  clear.addEventListener('click',()=>{
    for(const field of fields) field.checked=false;
    sync();
  });
  for(const control of [...fields,...caps]) control.addEventListener('change',sync);
  if(toolbar&&standard){
    toolbar.hidden=false;
    standard.addEventListener('click',()=>{
      for(const cap of caps)cap.checked=['calls:read','metrics:read'].includes(cap.value);
      for(const cap of caps)cap.dispatchEvent(new Event('change',{bubbles:true}));
      const baseFields=new Set(['id','CALLDATE','tellstate','tellside','aicallinfostate','voice_length','vw_danix_base_info_users_name','call_time']);
      for(const field of fields)field.checked=!field.disabled&&baseFields.has(field.value);
      sync();
    });
  }
  tools.hidden=false;sync();
}
