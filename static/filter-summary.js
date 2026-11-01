/**
 * Small presentation-only summary of the filters that produced a successful
 * call-list response. Raw source values and API parameters are not changed.
 * Grouping prevents a 20-item multi-select from flooding the mobile layout.
 */
export const REPORT_FACETS = Object.freeze([
  ['after', 'از تاریخ'],
  ['before', 'تا تاریخ'],
  ['operators', 'کارشناس'],
  ['destination', 'مقصد'],
  ['team', 'تیم'],
  ['call_type', 'نوع تماس'],
  ['state', 'وضعیت'],
  ['direction', 'جهت تماس'],
]);

/**
 * @param {URLSearchParams} params - query parameters used by a successful request
 * @param {object} options - optional display-only label functions
 * @returns {Array<{key:string,label:string,summary:string,count:number}>}
 */
export function appliedFilterGroups(params, {
  labelFor = (_key, raw) => raw,
  formatDate = raw => raw,
  formatCount = n => new Intl.NumberFormat('fa-IR').format(n),
} = {}) {
  const groups = [];
  for (const [key, label] of REPORT_FACETS) {
    // The report query may contain limit/offset and a fixed profile operator.
    // Only explicit user-selected facets belong in this summary.
    const values = [...new Set(params.getAll(key).filter(Boolean))];
    if (!values.length) continue;
    const displayed = values.map(raw => {
      const result = key === 'after' || key === 'before'
        ? formatDate(raw) : labelFor(key, raw);
      return String(result ?? raw);
    });
    const summary = displayed.length <= 2
      ? displayed.join('، ')
      : displayed.slice(0, 2).join('، ') + ' و ' +
        formatCount(displayed.length - 2) + ' مورد دیگر';
    groups.push({key, label, summary, count: values.length});
  }
  return groups;
}

/**
 * Keep selected raw values when a refreshed distinct-values endpoint omits
 * them. This does not invent filters or change what will be submitted.
 */
export function preserveSelectedFacetOptions(values, selectedOptions) {
  const previous=new Map([...selectedOptions]
    .filter(option=>option.value)
    .map(option=>[String(option.value),String(option.textContent||option.value)]));
  const fresh=new Set(values
    .filter(value=>value!==null&&value!==undefined&&String(value).trim())
    .map(String));
  return [...new Set([...fresh,...previous.keys()])].map(value=>({
    value, selected:previous.has(value), available:fresh.has(value),
    previousLabel:previous.get(value)||value
  }));
}
