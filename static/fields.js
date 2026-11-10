'use strict';
// Field checkboxes are convenience only. The server validates every write
// against actual role/capability grants and projects every reporting response.
const publicFields = new Set([
  'id','CALLDATE','tellstate','tellside','aicallinfostate','voice_length',
  'possibility_of_sale_ai','deal_value','vw_danix_base_info_users_name',
  'call_time'
]);
const sensitiveFields = new Set([
  'call_id','customername','customertell','outcome','ai_recommendation',
  'summary','tell_state_desc','create_date'
]);
const metricFields = new Set([
  'id','aicallinfostate','possibility_of_sale_ai','voice_length'
]);
for (const form of document.querySelectorAll('form[data-access-editor]')) {
  const columns = [...form.querySelectorAll('input[name="fields"]')];
  const grants = [...form.querySelectorAll('input[name="grants"]')];
  const role = form.querySelector('[data-role-select]');
  const group = form.querySelector('[data-group-select]');
  if (!columns.length || !role) continue;

  const allowedFields = () => {
    const caps = role.value === 'admin'
      ? new Set(['calls:read','calls:sensitive','calls:transcript:read','metrics:read'])
      : new Set(grants.filter(x => x.checked).map(x => x.value));
    const result = new Set();
    if (caps.has('calls:read')) {
      for (const name of publicFields) result.add(name);
      if (caps.has('calls:sensitive')) {
        for (const name of sensitiveFields) result.add(name);
      }
      // Transcription means an audited, redacted excerpt only.
      if (caps.has('calls:transcript:read')) result.add('transcription');
    }
    if (caps.has('metrics:read')) {
      for (const name of metricFields) result.add(name);
    }
    return result;
  };

  const sync = (reset = false) => {
    const allowed = allowedFields();
    for (const checkbox of columns) {
      const usable = allowed.has(checkbox.value);
      if (!usable) checkbox.checked = false;
      else if (reset) checkbox.checked = true;
      checkbox.disabled = !usable;
      checkbox.closest('label')?.classList.toggle('access-field-disabled', !usable);
    }
  };
  // Event handlers from users.js run first and update prerequisites.
  for (const checkbox of grants) checkbox.addEventListener('change', () => sync(true));
  role.addEventListener('change', () => sync(true));
  group?.addEventListener('change', () => sync(true));
  sync(false);
}
