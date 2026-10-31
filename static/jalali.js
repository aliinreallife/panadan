'use strict';
// Doran Web Components are locally bundled by `pnpm install && pnpm build`.
// These date inputs always send Gregorian ISO dates to the backend.
window.PanadanDate = (() => {
  const digit = (value) => String(value).replace(/[۰-۹]/g, c => '۰۱۲۳۴۵۶۷۸۹'.indexOf(c)).replace(/[٠-٩]/g, c => '٠١٢٣٤٥٦٧٨٩'.indexOf(c));
  const format = (date, opts = {}) => {
    if (!date) return '—';
    const input=String(date);
    const dateOnly=/^\d{4}-\d{2}-\d{2}$/.test(input);
    const iso=dateOnly?`${input}T12:00:00Z`:/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(input)?input.replace(' ','T')+'Z':input;
    const d=new Date(iso);
    return Number.isNaN(d.valueOf()) ? String(date) : new Intl.DateTimeFormat('fa-IR-u-ca-persian', Object.keys(opts).length ? opts : {year:'numeric',month:'2-digit',day:'2-digit', timeZone:'Asia/Tehran'}).format(d);
  };
  function ymd(jsDate) {
    const pad = x => String(x).padStart(2, '0');
    return `${jsDate.getFullYear()}-${pad(jsDate.getMonth()+1)}-${pad(jsDate.getDate())}`;
  }
  // Doran is a Web Component: its internal inputs and calendar may live in
  // shadow DOM, where dashboard CSS selectors do not apply.
  const calendarFont = "'Vazirmatn Variable', Vazirmatn, Tahoma, sans-serif";
  function applyCalendarFont(host) {
    if (!host) return;
    host.style.setProperty('font-family',calendarFont,'important');
    host.style.setProperty('--font-family',calendarFont);
    host.style.setProperty('--doran-font-family',calendarFont);
    const root=host.shadowRoot;
    if(root && !root.getElementById('panadan-doran-font')){
      const style=document.createElement('style');
      style.id='panadan-doran-font';
      style.textContent=`
        :host {font-family:${calendarFont} !important;font-synthesis:none}
        input,button,select,textarea,[role="dialog"],[role="grid"],[role="gridcell"],
        [role="button"],[role="textbox"],[part] {
          font-family:${calendarFont} !important;
          font-synthesis:none;
        }
      `;
      root.append(style);
    }
  }
  function installFont(host) {
    if(!host)return;
    applyCalendarFont(host);
    window.customElements.whenDefined('doran-datepicker').then(()=>{
      applyCalendarFont(host);
      requestAnimationFrame(()=>applyCalendarFont(host));
    });
    host.addEventListener('focusin',()=>applyCalendarFont(host));
    host.addEventListener('click',()=>applyCalendarFont(host));
  }
  const attach = (id) => {
    const host = document.getElementById(id + '-doran');
    const hidden = document.getElementById(id);
    if (!hidden) return;
    installFont(host);
    // Without the self-hosted component, native date inputs remain usable.
    if (!window.customElements.get('doran-datepicker')) {
      hidden.type = 'date'; hidden.hidden = false;
      if(host)host.hidden = true;
      return;
    }
    hidden.type = 'hidden';
    host.hidden = false;
    host.addEventListener('change', event => {
      const date = event.detail?.date;
      hidden.value = date ? ymd(date.toGregorian()) : '';
    });
  };
  const attachDateTime = (id) => {
    const host = document.getElementById(id + '-doran');
    const hidden = document.getElementById(id);
    if (!hidden) return;
    installFont(host);
    if (!window.customElements.get('doran-datepicker')) {
      hidden.type='datetime-local'; hidden.hidden=false;
      if(host)host.hidden=true;
      return;
    }
    hidden.type='hidden'; host.hidden=false;
    host.addEventListener('change', event => {
      const date=event.detail?.date;
      // ISO contains an offset/UTC timestamp; backend converts into UTC-naive Odoo storage.
      hidden.value=date ? date.toGregorian().toISOString() : '';
    });
  };
  return { format, digit, attach, attachDateTime };
})();
