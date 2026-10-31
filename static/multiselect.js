/** Compact searchable multi-selects.
 * Click a row to toggle selection; a checkmark appears on selected rows.
 * Multiple picks stay open until Escape, outside click, or focus leaves.
 * The underlying native <select multiple> remains the source of truth.
 */
export function multiValues(select) {
  return [...select.selectedOptions].map(option => option.value).filter(Boolean);
}
export function multiSummary(select, label) {
  const count = multiValues(select).length;
  return count ? label + ' · ' + new Intl.NumberFormat('fa-IR').format(count) + ' انتخاب'
               : 'همه ' + label;
}

/** Returns false without changing the option when the 20-value cap is reached. */
export function toggleMultiOption(option, selectedCount, max = 20) {
  if (option.disabled || (!option.selected && selectedCount >= max)) return false;
  option.selected = !option.selected;
  return true;
}

export function enhanceMultiSelects(root = globalThis.document) {
  if (!root?.querySelectorAll) return;
  for (const select of root.querySelectorAll('select[data-multi]')) {
    if (select.dataset.multiReady === 'true') continue;
    const doc = select.ownerDocument;
    const label = select.getAttribute('aria-label') || select.dataset.title || 'گزینه‌ها';
    const container = doc.createElement('div');
    container.className = 'ui-multi';

    const trigger = doc.createElement('button');
    trigger.type = 'button';
    trigger.className = 'ui-multi-trigger';
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.setAttribute('aria-label', 'فیلتر ' + label);
    const text = doc.createElement('span');
    text.className = 'ui-multi-value';
    const caret = doc.createElement('span');
    caret.textContent = '⌄';
    caret.setAttribute('aria-hidden', 'true');
    trigger.append(text, caret);
    container.append(trigger);
    select.before(container);

    const popup = doc.createElement('div');
    popup.className = 'ui-multi-popup';
    popup.hidden = true;
    const search = doc.createElement('input');
    search.type = 'search';
    search.className = 'ui-multi-search';
    search.placeholder = 'جستجو میان گزینه‌ها…';
    search.setAttribute('aria-label', 'جستجوی ' + label);
    const choices = doc.createElement('div');
    choices.className = 'ui-multi-options';
    choices.setAttribute('role', 'listbox');
    choices.setAttribute('aria-label', label);
    choices.setAttribute('aria-multiselectable', 'true');
    popup.append(search, choices);
    doc.body.append(popup);

    let opened = false;
    function sync() {
      text.textContent = multiSummary(select, label);
      container.classList.toggle('has-value', multiValues(select).length > 0);
    }
    function position() {
      if (!opened) return;
      const rect = trigger.getBoundingClientRect();
      const viewport = doc.documentElement.clientWidth;
      const width = Math.max(190, Math.min(340, viewport - 24));
      const left = Math.max(12, Math.min(rect.right - width, viewport - width - 12));
      popup.style.left = left + 'px';
      popup.style.width = width + 'px';
      const below = doc.documentElement.clientHeight - rect.bottom - 12;
      const above = rect.top - 12;
      const upward = below < 260 && above > below;
      const height = Math.min(390, Math.max(170, upward ? above : below));
      popup.style.maxHeight = height + 'px';
      popup.style.top = (upward ? Math.max(8, rect.top - height - 6) : rect.bottom + 6) + 'px';
    }
    function render() {
      const query = search.value.trim().toLocaleLowerCase('fa');
      choices.replaceChildren();
      let matches = 0;
      for (const option of select.options) {
        if (!option.value || (query && !option.textContent.trim().toLocaleLowerCase('fa').includes(query))) continue;
        matches++;
        const row = doc.createElement('button');
        row.type = 'button';
        row.className = 'ui-multi-option';
        row.setAttribute('role', 'option');
        row.disabled = option.disabled;
        row.setAttribute('aria-selected', String(option.selected));
        const name = doc.createElement('span');
        name.className = 'ui-multi-option-name';
        name.textContent = option.textContent;
        const tick = doc.createElement('span');
        tick.className = 'ui-multi-check';
        tick.textContent = '✓';
        tick.setAttribute('aria-hidden', 'true');
        row.append(name, tick);
        row.addEventListener('click', () => {
          if (!toggleMultiOption(option, multiValues(select).length)) {
            let note = choices.querySelector('.ui-multi-limit');
            if (!note) {
              note = doc.createElement('p');
              note.className = 'ui-multi-limit';
              note.setAttribute('role', 'status');
              choices.prepend(note);
            }
            note.textContent = 'حداکثر ۲۰ گزینه قابل انتخاب است';
            return;
          }
          row.setAttribute('aria-selected', String(option.selected));
          select.dispatchEvent(new Event('change', { bubbles: true }));
          sync();
          // Keep the row focused and the menu open for the next selection.
        });
        choices.append(row);
      }
      if (!matches) {
        const empty = doc.createElement('p');
        empty.className = 'ui-multi-empty';
        empty.textContent = 'گزینه‌ای پیدا نشد';
        choices.append(empty);
      }
    }
    function close({ restoreFocus = false } = {}) {
      if (!opened) return;
      opened = false;
      popup.hidden = true;
      trigger.setAttribute('aria-expanded', 'false');
      if (restoreFocus) trigger.focus();
    }
    function open() {
      if (opened) return;
      for (const other of doc.querySelectorAll('.ui-multi-popup:not([hidden])')) {
        if (other !== popup) other.dispatchEvent(new Event('multi-close'));
      }
      opened = true;
      popup.hidden = false;
      trigger.setAttribute('aria-expanded', 'true');
      search.value = '';
      render();
      position();
      search.focus();
    }
    popup.addEventListener('multi-close', () => close());
    trigger.addEventListener('click', () => opened ? close() : open());
    search.addEventListener('input', render);
    popup.addEventListener('keydown', event => {
      if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp' &&
          event.key !== 'Home' && event.key !== 'End') return;
      const rows = [...choices.querySelectorAll('[role="option"]:not([disabled])')];
      if (!rows.length) return;
      event.preventDefault();
      const current = rows.indexOf(doc.activeElement);
      let next;
      if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = rows.length - 1;
      else if (event.key === 'ArrowDown') next = current < 0 ? 0 : (current + 1) % rows.length;
      else next = current < 0 ? rows.length - 1 : (current - 1 + rows.length) % rows.length;
      rows[next].focus();
    });
    doc.addEventListener('pointerdown', event => {
      if (opened && !container.contains(event.target) && !popup.contains(event.target)) close();
    });
    doc.addEventListener('focusin', event => {
      if (opened && !container.contains(event.target) && !popup.contains(event.target)) close();
    });
    doc.addEventListener('keydown', event => {
      if (!opened) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        close({ restoreFocus: true });
      }
    });
    doc.defaultView?.addEventListener('resize', position, { passive: true });
    doc.defaultView?.addEventListener('scroll', position, { passive: true, capture: true });
    new MutationObserver(() => { sync(); if (opened) render(); })
      .observe(select, { childList: true, subtree: true, attributes: true });
    select.dataset.multiReady = 'true';
    select.classList.add('ui-multi-native');
    select.tabIndex = -1;
    select.setAttribute('aria-hidden', 'true');
    sync();
  }
}
