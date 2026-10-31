/** Panadan's mobile navigation: four fixed bottom button tabs, following
 * the ULTOR pattern. Only expose routes present in the permission-filtered
 * server-rendered sidebar. Desktop navigation remains unchanged.
 */
(function () {
  const sidebar = document.querySelector('.shell > .sidebar');
  const nav = sidebar?.querySelector('nav');
  if (!sidebar || !nav || sidebar.querySelector('.mobile-nav')) return;

  const links = [...nav.querySelectorAll('a[href]')];
  const groups = [
    {id:'report',label:'گزارش‌ها',glyph:'▦',
      paths:['/dashboard'],main:'/dashboard'},
    {id:'operators',label:'کارشناسان',glyph:'♙',
      paths:['/dashboard/operators'],main:'/dashboard/operators'},
    {id:'integrations',label:'اتصالات',glyph:'◈',
      paths:['/dashboard/connect','/dashboard/tokens','/dashboard/api','/dashboard/oauth']},
    {id:'management',label:'مدیریت',glyph:'▤',
      paths:['/dashboard/users','/dashboard/activity']}
  ];
  const current = window.location.pathname;
  const mobile = document.createElement('div');
  mobile.className = 'mobile-nav';
  mobile.setAttribute('role', 'navigation');
  mobile.setAttribute('aria-label', 'ناوبری اصلی موبایل');

  let menu = null;
  let opener = null;

  function close({restoreFocus = false} = {}) {
    const previous = opener;
    menu?.remove();
    menu = null;
    opener?.setAttribute('aria-expanded', 'false');
    opener = null;
    if (restoreFocus) previous?.focus();
  }

  function openMenu(button, group, available) {
    if (opener === button) {
      close({restoreFocus: true});
      return;
    }
    close();
    opener = button;
    button.setAttribute('aria-expanded', 'true');

    menu = document.createElement('div');
    menu.className = 'mobile-nav-menu';
    menu.setAttribute('role', 'group');
    menu.setAttribute('aria-label', 'بخش‌های ' + group.label);
    for (const source of available) {
      const item = document.createElement('a');
      item.href = source.href;
      // Text is taken from the server-rendered permitted sidebar.
      item.textContent = source.textContent.trim();
      const isCurrent = new URL(source.href).pathname === current;
      if (isCurrent) {
        item.className = 'is-current';
        item.setAttribute('aria-current', 'page');
      }
      menu.append(item);
    }
    sidebar.append(menu);
    const currentLink = menu.querySelector('[aria-current="page"]');
    (currentLink || menu.querySelector('a'))?.focus();
  }

  for (const group of groups) {
    const available = links.filter(a => group.paths.includes(new URL(a.href).pathname));
    if (!available.length) continue;
    const active = group.paths.some(path => path === current) ||
                   (group.id === 'operators' && current === '/dashboard/operator');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'mobile-nav-tab' + (active ? ' is-active' : '');
    button.setAttribute('aria-label', group.label);
    button.setAttribute('aria-expanded', 'false');
    if (active) button.setAttribute('aria-current', 'page');

    const glyph = document.createElement('span');
    glyph.className = 'mobile-nav-glyph';
    glyph.textContent = group.glyph;
    glyph.setAttribute('aria-hidden', 'true');
    const label = document.createElement('span');
    label.className = 'mobile-nav-text';
    label.textContent = group.label;
    button.append(glyph, label);
    button.addEventListener('click', () => {
      // Single-destination buttons navigate directly; combined groups open
      // the short, ULTOR-style destination chooser above the bottom bar.
      if (available.length === 1) {
        close();
        window.location.assign(available[0].href);
      } else {
        openMenu(button, group, available);
      }
    });
    mobile.append(button);
  }
  if (!mobile.children.length) return;
  sidebar.append(mobile);
  sidebar.classList.add('mobile-nav-ready');

  document.addEventListener('pointerdown', event => {
    if (menu && !mobile.contains(event.target) && !menu.contains(event.target)) close();
  });
  document.addEventListener('focusin', event => {
    if (menu && !mobile.contains(event.target) && !menu.contains(event.target)) close();
  });
  document.addEventListener('keydown', event => {
    if (menu && event.key === 'Escape') {
      event.preventDefault();
      close({restoreFocus: true});
    }
  });
  window.addEventListener('resize', () => {
    if (menu && window.innerWidth > 800) close();
  });
})();
