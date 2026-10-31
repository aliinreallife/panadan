// Display-only vocabulary. Never modify raw reporting values or filter keys.
// If the upstream system adds a value, display its original text instead of guessing.
const normalize = value => String(value ?? '').trim().replace(/[\s_-]+/g, '').toLowerCase();
const CALL_TYPES = Object.freeze({
  followup: 'پیگیری',
  firsttoch: 'تماس اول',
  firsttouch: 'تماس اول',
  colleague: 'همکار',
  unknown: 'نامشخص'
});
const AI_STATES = Object.freeze({
  soldout: 'فروش رفته',
  unchecked: 'بررسی‌نشده',
  inprocess: 'در حال بررسی',
  canceled: 'لغوشده',
  cancelled: 'لغوشده',
  systeminvalid: 'نامعتبر سیستمی',
  userinvalid: 'نامعتبر کاربری'
});
export function callTypeLabel(value) {
  if (value === null || value === undefined || !String(value).trim()) return '—';
  return CALL_TYPES[normalize(value)] ?? String(value);
}
export function callStateLabel(value) {
  if (value === null || value === undefined || !String(value).trim()) return '—';
  return AI_STATES[normalize(value)] ?? String(value);
}
export function knownTypeOptions() {
  return ['FirstToch', 'FollowUp', 'Colleague', 'Unknown'];
}
export function knownStateOptions() {
  return ['SoldOut', 'Unchecked', 'Inprocess', 'Canceled', 'System Invalid', 'User Invalid'];
}

const DIRECTIONS = Object.freeze({
  intoout: 'خروجی',
  outtoin: 'ورودی'
});
export function directionLabel(value) {
  if(value === null || value === undefined || !String(value).trim())return '—';
  return DIRECTIONS[normalize(value)] ?? String(value);
}
