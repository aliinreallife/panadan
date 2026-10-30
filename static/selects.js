/**
 * Accessible, progressively-enhanced select controls for Panadan.
 *
 * Original <select> is always retained for forms, validation and no-JS fallback.
 * The menu is rendered at document.body so it is not clipped by scrolling
 * tables or dashboard filter panels. No external dependencies.
 */
let serial = 0;
let currentlyOpen = null;

export function normalizeSearch(value) {
  return String(value ?? '').trim().toLocaleLowerCase('fa')
    .replace(/[يى]/g, 'ی').replace(/ك/g, 'ک')
    .replace(/[\u064b-\u065f]/g, '')
    .replace(/[۰-۹٠-٩]/g, d => {
      const a='۰۱۲۳۴۵۶۷۸۹', b='٠١٢٣٤٥٦٧٨٩';
      return String(a.includes(d)?a.indexOf(d):b.indexOf(d));
    });
}

export function selectOptions(select) {
  return [...select.options].map((option,index)=>({
    index, value:option.value, label:option.textContent.trim(),
    hint:option.title || '', disabled:option.disabled, selected:option.selected
  }));
}

export function visibleOptions(options, query='') {
  const term=normalizeSearch(query);
  return options.filter(option=>!term ||
    normalizeSearch(option.label).includes(term) ||
    normalizeSearch(option.hint).includes(term));
}

export function nextEnabledIndex(options, start, movement) {
  if (!options.length) return -1;
  if (movement==='first') return options.findIndex(x=>!x.disabled);
  if (movement==='last') return options.findLastIndex(x=>!x.disabled);
  const step=movement==='previous'?-1:1;
  for(let n=1;n<=options.length;n++){
    const index=(start+step*n+options.length*2)%options.length;
    if(!options[index].disabled)return index;
  }
  return -1;
}

function labelFor(select) {
  const label=select.closest('label');
  const text=label && [...label.childNodes]
    .filter(n=>n.nodeType===3).map(n=>n.textContent).join(' ').trim();
  return select.getAttribute('aria-label') || text || select.name || 'انتخاب گزینه';
}

function enhanceSelect(select) {
  if(select.dataset.selectReady==='true' || select.disabled || !select.options.length) return;
  const doc=select.ownerDocument;
  const label=labelFor(select);
  const id='panadan-select-'+(++serial);
  const searchMode=select.hasAttribute('data-searchable') || select.options.length>8;

  const root=doc.createElement('div');
  root.className='ui-select';
  const trigger=doc.createElement('button');
  trigger.type='button';
  trigger.className='ui-select-trigger';
  trigger.setAttribute('role','combobox');
  trigger.setAttribute('aria-haspopup','listbox');
  trigger.setAttribute('aria-expanded','false');
  trigger.setAttribute('aria-controls',id+'-menu');
  trigger.setAttribute('aria-label',label);
  const text=doc.createElement('span');
  text.className='ui-select-value';
  const caret=doc.createElement('span');
  caret.className='ui-select-caret';
  caret.setAttribute('aria-hidden','true');
  trigger.append(text,caret);
  const clear=doc.createElement('button');
  clear.type='button';
  clear.className='ui-select-clear';
  clear.textContent='×';
  clear.setAttribute('aria-label','پاک کردن '+label);
  clear.title='پاک کردن انتخاب';
  root.append(trigger,clear);
  select.after(root);

  const menu=doc.createElement('div');
  menu.className='ui-select-menu';
  menu.id=id+'-popup';
  menu.hidden=true;
  const search=doc.createElement('input');
  search.type='search';
  search.className='ui-select-search';
  search.autocomplete='off';
  search.placeholder='جستجو میان گزینه‌ها…';
  search.setAttribute('aria-label','جستجو در '+label);
  search.setAttribute('aria-controls',id+'-menu');
  search.spellcheck=false;
  const list=doc.createElement('div');
  list.className='ui-select-options';
  list.id=id+'-menu';
  list.setAttribute('role','listbox');
  list.setAttribute('aria-label',label);
  let visible=[],active=-1,open=false;
  if(searchMode){
    const searchArea=doc.createElement('div');
    searchArea.className='ui-select-search-wrap';
    searchArea.append(search);
    menu.append(searchArea);
  }
  menu.append(list);
  doc.body.append(menu);

  function sync() {
    const current=select.selectedOptions[0];
    text.textContent=current?.textContent?.trim() || 'انتخاب کنید';
    text.title=current?.title || '';
    root.classList.toggle('ui-select-has-value',Boolean(select.value));
    clear.hidden=!(select.options.length && [...select.options].some(o=>o.value==='') && Boolean(select.value));
    trigger.disabled=select.disabled;
  }
  function placement(){
    if(!open)return;
    const rect=trigger.getBoundingClientRect();
    const width=Math.min(Math.max(rect.width,220),doc.documentElement.clientWidth-24);
    const left=Math.max(12,Math.min(rect.left,doc.documentElement.clientWidth-width-12));
    const availableDown=doc.documentElement.clientHeight-rect.bottom-12;
    const availableUp=rect.top-12;
    const useAbove=availableDown<230&&availableUp>availableDown;
    const available=Math.max(130,useAbove?availableUp:availableDown);
    menu.style.width=width+'px';
    menu.style.left=left+'px';
    menu.style.maxHeight=Math.min(350,available)+'px';
    const height=Math.min(menu.scrollHeight,350,available);
    menu.style.top=(useAbove?Math.max(12,rect.top-height-6):rect.bottom+6)+'px';
    menu.classList.toggle('ui-select-above',useAbove);
  }
  function activeTo(index) {
    if(index<0||index>=visible.length||visible[index].disabled)return;
    active=index;
    for(const [i,option] of [...list.children].entries()){
      option.classList.toggle('ui-select-focused',i===active);
    }
    const node=list.children[active];
    if(node){
      trigger.setAttribute('aria-activedescendant',node.id);
      if(searchMode)search.setAttribute('aria-activedescendant',node.id);
      node.scrollIntoView({block:'nearest'});
    }
  }
  function render(query=''){
    visible=visibleOptions(selectOptions(select),query);
    list.replaceChildren();
    for(let i=0;i<visible.length;i++){
      const item=visible[i];
      const option=doc.createElement('div');
      option.id=id+'-option-'+item.index;
      option.setAttribute('role','option');
      option.setAttribute('aria-selected',String(item.selected));
      option.setAttribute('aria-disabled',String(item.disabled));
      option.className='ui-select-option';
      const optionText=doc.createElement('span');
      optionText.className='ui-select-option-label';
      optionText.textContent=item.label;
      const mark=doc.createElement('span');
      mark.className='ui-select-check';
      mark.setAttribute('aria-hidden','true');
      mark.textContent=item.selected?'✓':'';
      option.append(optionText,mark);
      if(item.hint)option.title=item.hint;
      if(item.disabled)option.classList.add('ui-select-disabled');
      option.addEventListener('click',()=>{
        if(!item.disabled)choose(item);
      });
      list.append(option);
    }
    if(!visible.length)list.append(Object.assign(doc.createElement('p'),{
      className:'ui-select-empty',textContent:'گزینه‌ای پیدا نشد'
    }));
    const selected=visible.findIndex(o=>o.selected&&!o.disabled);
    active=selected>=0?selected:nextEnabledIndex(visible,-1,'next');
    if(active>=0)activeTo(active);
    else {
      trigger.removeAttribute('aria-activedescendant');
      search.removeAttribute('aria-activedescendant');
    }
    placement();
  }
  function choose(item) {
    select.value=item.value;
    select.dispatchEvent(new Event('input',{bubbles:true}));
    select.dispatchEvent(new Event('change',{bubbles:true}));
    sync();
    close(true);
  }
  function close(restoreFocus=false){
    if(!open)return;
    open=false;
    currentlyOpen=null;
    root.classList.remove('ui-select-open');
    menu.hidden=true;
    trigger.setAttribute('aria-expanded','false');
    trigger.removeAttribute('aria-activedescendant');
    search.removeAttribute('aria-activedescendant');
    if(restoreFocus)trigger.focus();
  }
  function show(){
    if(open||trigger.disabled)return;
    currentlyOpen?.();
    open=true;
    currentlyOpen=()=>close();
    root.classList.add('ui-select-open');
    menu.hidden=false;
    trigger.setAttribute('aria-expanded','true');
    search.value='';
    render();
    placement();
    if(searchMode)search.focus();else trigger.focus();
  }
  function key(event){
    if(!open){
      if(['ArrowDown','ArrowUp','Enter',' '].includes(event.key)){
        event.preventDefault();show();
      }
      return;
    }
    if(event.key==='Escape'){event.preventDefault();close(true);return;}
    if(event.key==='Tab'){close();return;}
    if(event.key==='ArrowDown'||event.key==='ArrowUp'){
      event.preventDefault();
      activeTo(nextEnabledIndex(visible,active,event.key==='ArrowDown'?'next':'previous'));
    }else if((event.key==='Home'||event.key==='End')&&event.target!==search){
      event.preventDefault();activeTo(nextEnabledIndex(visible,active,event.key==='Home'?'first':'last'));
    }else if(event.key==='Enter'||(event.key===' '&&!searchMode)){
      event.preventDefault();
      if(visible[active]&&!visible[active].disabled)choose(visible[active]);
    }else if(!searchMode&&event.key.length===1&&!event.ctrlKey&&!event.metaKey){
      const matching=visible.findIndex(x=>!x.disabled&&normalizeSearch(x.label).startsWith(normalizeSearch(event.key)));
      if(matching>=0)activeTo(matching);
    }
  }
  trigger.addEventListener('click',()=>open?close():show());
  trigger.addEventListener('keydown',key);
  search.addEventListener('keydown',key);
  search.addEventListener('input',()=>render(search.value));
  clear.addEventListener('click',()=>{
    const empty=[...select.options].find(o=>o.value==='');
    if(!empty)return;
    select.value='';
    select.dispatchEvent(new Event('input',{bubbles:true}));
    select.dispatchEvent(new Event('change',{bubbles:true}));
    sync();
  });
  select.addEventListener('change',sync);
  const outside=event=>{
    if(open&&!root.contains(event.target)&&!menu.contains(event.target))close();
  };
  const moved=()=>placement();
  doc.addEventListener('pointerdown',outside);
  doc.addEventListener('keydown',event=>{
    if(open&&event.key==='Escape'&&!menu.contains(event.target)&&!root.contains(event.target))close();
  });
  doc.defaultView?.addEventListener('resize',moved,{passive:true});
  doc.defaultView?.addEventListener('scroll',moved,{passive:true,capture:true});
  const observer=new MutationObserver(()=>{
    sync();
    if(open)render(search.value);
  });
  observer.observe(select,{attributes:true,childList:true,subtree:true,characterData:true});
  select.form?.addEventListener('reset',()=>queueMicrotask(sync));
  select.dataset.selectReady='true';
  select.tabIndex=-1;
  select.setAttribute('aria-hidden','true');
  select.classList.add('ui-select-native');
  sync();
}

export function enhanceSelects(root=globalThis.document) {
  if(!root || typeof root.querySelectorAll!=='function')return;
  for(const select of root.querySelectorAll('select:not([data-no-enhance])'))enhanceSelect(select);
}
