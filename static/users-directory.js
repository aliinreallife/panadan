'use strict';

// User search and filters are presentation-only. Account permissions and
// changes remain enforced exclusively by the server.
(() => {
  const list = document.getElementById('access-users-list');
  if (!list) return;
  const search = document.getElementById('access-user-search');
  const status = document.getElementById('access-user-status');
  const role = document.getElementById('access-user-role');
  const counter = document.getElementById('access-visible-count');
  const empty = document.getElementById('access-users-empty');
  const cards = Array.from(list.querySelectorAll('[data-user-name]'));
  const normalize = value => String(value || '').trim().toLocaleLowerCase();

  const refresh = () => {
    const query = normalize(search?.value);
    let visible = 0;
    for (const card of cards) {
      const matchesName = normalize(card.dataset.userName).includes(query);
      const matchesRole = role?.value === 'all' || card.dataset.userRole === role?.value;
      const matchesStatus = status?.value === 'all' ||
        (status?.value === 'active' && card.dataset.userActive === 'true') ||
        (status?.value === 'inactive' && card.dataset.userActive === 'false');
      const show = matchesName && matchesRole && matchesStatus;
      card.hidden = !show;
      if (show) visible++;
    }
    if (counter) counter.textContent = new Intl.NumberFormat('fa-IR').format(visible) + ' کاربر';
    if (empty) empty.hidden = visible > 0 || cards.length === 0;
  };
  search?.addEventListener('input', refresh);
  status?.addEventListener('change', refresh);
  role?.addEventListener('change', refresh);
  refresh();

  const create = document.getElementById('create-user');
  const openFromHash = () => {
    if (create && window.location.hash === '#create-user') create.open = true;
  };
  window.addEventListener('hashchange', openFromHash);
  openFromHash();
})();
