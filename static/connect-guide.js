'use strict';
const tabList=document.querySelector('[data-guide-tabs]');
if(tabList){
 const tabs=Array.from(tabList.querySelectorAll('[data-guide-tab]'));
 const panels=Array.from(document.querySelectorAll('[data-guide-panel]'));
 const pairs=tabs.map(tab=>({tab,panel:panels.find(p=>p.dataset.guidePanel===tab.dataset.guideTab)}));
 if(pairs.length&&pairs.every(p=>p.panel)){
  tabList.setAttribute('role','tablist');
  const activate=(name,focus=false,writeHash=false)=>{
   const chosen=pairs.find(p=>p.tab.dataset.guideTab===name)||pairs[0];
   for(const pair of pairs){
    const active=pair===chosen;
    pair.tab.setAttribute('role','tab');
    pair.tab.setAttribute('aria-controls',pair.panel.id);
    pair.tab.setAttribute('aria-selected',String(active));
    pair.tab.tabIndex=active?0:-1;
    pair.panel.setAttribute('role','tabpanel');
    pair.panel.setAttribute('aria-labelledby',pair.tab.id);
    pair.panel.hidden=!active;
   }
   if(writeHash&&location.hash!=='#'+chosen.panel.id)history.replaceState(null,'','#'+chosen.panel.id);
   if(focus)chosen.tab.focus();
  };
  for(const [index,pair] of pairs.entries()){
   pair.tab.addEventListener('click',e=>{e.preventDefault();activate(pair.tab.dataset.guideTab,false,true);});
   pair.tab.addEventListener('keydown',e=>{
    let next=index;
    if(e.key==='ArrowLeft')next=(index+1)%pairs.length;
    else if(e.key==='ArrowRight')next=(index-1+pairs.length)%pairs.length;
    else if(e.key==='Home')next=0;
    else if(e.key==='End')next=pairs.length-1;
    else if(e.key!==' '&&e.key!=='Enter')return;
    e.preventDefault();activate(pairs[next].tab.dataset.guideTab,true,true);
   });
  }
  activate(location.hash.slice(1));
  window.addEventListener('hashchange',()=>activate(location.hash.slice(1)));
 }
}
for(const button of document.querySelectorAll('[data-guide-copy]')){
 button.addEventListener('click',async()=>{
  const status=button.closest('.panel')?.querySelector('.guide-copy-status');
  try{
   await navigator.clipboard.writeText(button.dataset.guideCopy);
   if(status)status.textContent='کپی شد.';
   const original=button.dataset.originalLabel||button.textContent;
   button.dataset.originalLabel=original;
   button.textContent='کپی شد';
   clearTimeout(button.copyReset);
   button.copyReset=setTimeout(()=>{button.textContent=original;},1800);
  }catch{if(status)status.textContent='کپی خودکار ممکن نیست؛ مقدار را انتخاب و دستی کپی کنید.';}
 });
}
