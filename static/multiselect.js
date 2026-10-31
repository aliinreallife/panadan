/** Searchable multi-value report filter. Original <select multiple> remains
 * the form/source-of-truth; options are never converted into query strings
 * until the report is submitted. No external dependencies. */
export function multiValues(select) {
  return [...select.selectedOptions].map(option=>option.value).filter(Boolean);
}
export function multiSummary(select, label) {
  const count=multiValues(select).length;
  return count ? label+' · '+new Intl.NumberFormat('fa-IR').format(count)+' انتخاب'
               : 'همه '+label;
}
export function enhanceMultiSelects(root=globalThis.document) {
  if(!root?.querySelectorAll)return;
  for(const select of root.querySelectorAll('select[data-multi]')){
    if(select.dataset.multiReady==='true')continue;
    const doc=select.ownerDocument;
    const label=select.getAttribute('aria-label')||select.dataset.title||'گزینه‌ها';
    const container=doc.createElement('div');
    container.className='ui-multi';
    const trigger=doc.createElement('button');
    trigger.type='button';
    trigger.className='ui-multi-trigger';
    trigger.setAttribute('aria-haspopup','dialog');
    trigger.setAttribute('aria-expanded','false');
    trigger.setAttribute('aria-label','فیلتر '+label);
    const text=doc.createElement('span');
    text.className='ui-multi-value';
    const caret=doc.createElement('span');caret.textContent='⌄';caret.setAttribute('aria-hidden','true');
    trigger.append(text,caret);container.append(trigger);
    select.before(container);
    const popup=doc.createElement('div');
    popup.className='ui-multi-popup';
    popup.setAttribute('role','dialog');
    popup.setAttribute('aria-label','انتخاب '+label);
    popup.hidden=true;
    const search=doc.createElement('input');
    search.type='search';search.className='ui-multi-search';
    search.placeholder='جستجو…';search.setAttribute('aria-label','جستجوی '+label);
    const choices=doc.createElement('div');choices.className='ui-multi-options';
    const footer=doc.createElement('div');footer.className='ui-multi-footer';
    const reset=doc.createElement('button');reset.type='button';reset.className='ui-multi-reset';reset.textContent='پاک کردن';
    const done=doc.createElement('button');done.type='button';done.className='ui-multi-done';done.textContent='تأیید';
    footer.append(reset,done);popup.append(search,choices,footer);doc.body.append(popup);
    let opened=false;
    function sync(){
      text.textContent=multiSummary(select,label);
      container.classList.toggle('has-value',multiValues(select).length>0);
    }
    function position(){
      if(!opened)return;
      const rect=trigger.getBoundingClientRect();
      const viewport=doc.documentElement.clientWidth;
      const width=Math.max(190,Math.min(340,viewport-24));
      const left=Math.max(12,Math.min(rect.right-width,viewport-width-12));
      popup.style.left=left+'px';popup.style.width=width+'px';
      const below=doc.documentElement.clientHeight-rect.bottom-12;
      const above=rect.top-12;
      const upward=below<260&&above>below;
      const height=Math.min(390,Math.max(170,upward?above:below));
      popup.style.maxHeight=height+'px';
      popup.style.top=(upward?Math.max(8,rect.top-height-6):rect.bottom+6)+'px';
    }
    function render(){
      const query=search.value.trim().toLocaleLowerCase('fa');
      choices.replaceChildren();
      let matches=0;
      for(const option of select.options){
        if(!option.value)continue;
        if(query&&!option.textContent.trim().toLocaleLowerCase('fa').includes(query))continue;
        matches++;
        const item=doc.createElement('label');item.className='ui-multi-option';
        const check=doc.createElement('input');
        check.type='checkbox';check.checked=option.selected;check.disabled=option.disabled;
        const name=doc.createElement('span');name.textContent=option.textContent;
        item.append(check,name);
        check.addEventListener('change',()=>{
          if(check.checked && multiValues(select).length>=20){
            check.checked=false;
            const message=choices.querySelector('.ui-multi-limit');
            if(!message){const note=doc.createElement('p');note.className='ui-multi-limit';note.textContent='حداکثر ۲۰ گزینه';choices.prepend(note);}
            return;
          }
          option.selected=check.checked;
          select.dispatchEvent(new Event('change',{bubbles:true}));
          sync();
        });
        choices.append(item);
      }
      if(!matches){const empty=doc.createElement('p');empty.className='ui-multi-empty';empty.textContent='گزینه‌ای پیدا نشد';choices.append(empty);}
    }
    function close(){
      if(!opened)return;
      opened=false;popup.hidden=true;trigger.setAttribute('aria-expanded','false');
      trigger.focus();
    }
    function open(){
      if(opened)return;
      for(const other of doc.querySelectorAll('.ui-multi-popup:not([hidden])')){
        if(other!==popup)other.dispatchEvent(new Event('multi-close'));
      }
      opened=true;popup.hidden=false;trigger.setAttribute('aria-expanded','true');
      search.value='';render();position();search.focus();
    }
    popup.addEventListener('multi-close',close);
    trigger.addEventListener('click',()=>opened?close():open());
    search.addEventListener('input',render);
    reset.addEventListener('click',()=>{
      for(const option of select.options)option.selected=false;
      select.dispatchEvent(new Event('change',{bubbles:true}));sync();render();
    });
    done.addEventListener('click',close);
    doc.addEventListener('pointerdown',event=>{
      if(opened&&!container.contains(event.target)&&!popup.contains(event.target))close();
    });
    doc.addEventListener('keydown',event=>{
      if(!opened)return;
      if(event.key==='Escape'){event.preventDefault();close();}
      if(event.key==='Tab'&&popup.contains(event.target)){
        const focusable=[search,...popup.querySelectorAll('input:not([disabled]),button')];
        if(event.shiftKey&&event.target===focusable[0]){event.preventDefault();focusable.at(-1).focus();}
        else if(!event.shiftKey&&event.target===focusable.at(-1)){event.preventDefault();focusable[0].focus();}
      }
    });
    doc.defaultView?.addEventListener('resize',position,{passive:true});
    doc.defaultView?.addEventListener('scroll',position,{passive:true,capture:true});
    new MutationObserver(()=>{sync();if(opened)render();}).observe(select,{childList:true,subtree:true,attributes:true});
    select.dataset.multiReady='true';
    select.classList.add('ui-multi-native');select.tabIndex=-1;select.setAttribute('aria-hidden','true');
    sync();
  }
}
