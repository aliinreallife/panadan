/** Four grouped mobile navigation buttons. Uses only routes already present
 * in the server-rendered sidebar, so hidden permission groups stay hidden.
 * Desktop sidebar remains untouched; no-JS mobile keeps original navigation.
 */
(function(){
  const sidebar=document.querySelector('.shell > .sidebar');
  const nav=sidebar?.querySelector('nav');
  if(!sidebar||!nav||sidebar.querySelector('.mobile-nav'))return;
  const links=[...nav.querySelectorAll('a[href]')];
  const groups=[
    {id:'report',label:'گزارش‌ها',glyph:'▦',paths:['/dashboard'],main:'/dashboard'},
    {id:'operators',label:'کارشناسان',glyph:'♙',paths:['/dashboard/operators'],main:'/dashboard/operators'},
    {id:'integrations',label:'اتصالات',glyph:'◈',paths:['/dashboard/connect','/dashboard/tokens','/dashboard/api','/dashboard/oauth']},
    {id:'management',label:'مدیریت',glyph:'▤',paths:['/dashboard/users','/dashboard/activity']}
  ];
  const current=window.location.pathname;
  const mobile=document.createElement('div');
  mobile.className='mobile-nav';
  mobile.setAttribute('aria-label','بخش‌های اصلی');
  let menu=null, opener=null;
  function close(){
    if(menu){menu.remove();menu=null;}
    if(opener){opener.setAttribute('aria-expanded','false');opener=null;}
  }
  for(const group of groups){
    const available=links.filter(a=>group.paths.includes(new URL(a.href).pathname));
    if(!available.length)continue;
    const active=group.paths.some(p=>current===p)||
                 (group.id==='report'&&current==='/dashboard/operator');
    const simple=group.main&&available.some(a=>new URL(a.href).pathname===group.main);
    const tab=document.createElement(simple?'a':'button');
    tab.className='mobile-nav-tab'+(active?' is-active':'');
    const glyph=document.createElement('span');glyph.className='mobile-nav-glyph';
    glyph.textContent=group.glyph;glyph.setAttribute('aria-hidden','true');
    const name=document.createElement('span');name.className='mobile-nav-text';
    name.textContent=group.label;tab.append(glyph,name);
    if(simple){
      tab.href=group.main;
      if(active)tab.setAttribute('aria-current','page');
    }else{
      tab.type='button';
      tab.setAttribute('aria-expanded','false');
      tab.setAttribute('aria-haspopup','true');
      tab.addEventListener('click',()=>{
        if(opener===tab){close();return;}
        close();opener=tab;tab.setAttribute('aria-expanded','true');
        menu=document.createElement('div');menu.className='mobile-nav-menu';
        menu.setAttribute('role','group');
        menu.setAttribute('aria-label',group.label);
        for(const link of available){
          const item=document.createElement('a');
          item.href=link.href;item.textContent=link.textContent.trim();
          if(new URL(link.href).pathname===current){item.className='is-current';item.setAttribute('aria-current','page');}
          menu.append(item);
        }
        sidebar.append(menu);
        menu.querySelector('a')?.focus();
      });
    }
    mobile.append(tab);
  }
  if(!mobile.children.length)return;
  sidebar.append(mobile);
  sidebar.classList.add('mobile-nav-ready');
  document.addEventListener('pointerdown',event=>{
    if(menu&&!mobile.contains(event.target)&&!menu.contains(event.target))close();
  });
  document.addEventListener('keydown',event=>{
    if(menu&&event.key==='Escape'){event.preventDefault();close();opener?.focus();}
  });
})();
