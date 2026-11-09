'use strict';
// A human user approves a verified OAuth client. The server never accepts
// model-provided client IDs or privileges to authorize data requests.
const callCols = new Set([
  'id','CALLDATE','tellstate','tellside','aicallinfostate','voice_length',
  'possibility_of_sale_ai','deal_value','vw_danix_base_info_users_name','call_time'
]);
const metricCols = new Set(['id','aicallinfostate','possibility_of_sale_ai','voice_length']);
for (const form of document.querySelectorAll('.mcp-consent-form')) {
  const capabilityChecks = [...form.querySelectorAll('input[name="capabilities"]')];
  const fields = [...form.querySelectorAll('input[name="fields"]')];
  const recalculate = () => {
    const caps = new Set(capabilityChecks.filter(x => x.checked).map(x => x.value));
    for (const checkbox of fields) {
      const permitted = (caps.has('calls:read') && callCols.has(checkbox.value)) ||
        (caps.has('metrics:read') && metricCols.has(checkbox.value)) ||
        (caps.has('calls:transcript:read') && caps.has('calls:read') &&
         checkbox.value === 'transcription');
      if (!permitted) checkbox.checked = false;
      checkbox.disabled = !permitted;
      checkbox.closest('label')?.classList.toggle('access-field-disabled', !permitted);
    }
  };
  for (const check of capabilityChecks) check.addEventListener('change', recalculate);
  recalculate();
}
