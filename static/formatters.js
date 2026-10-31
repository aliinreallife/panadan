// Presentation-only formatters. Reporting API values stay unchanged.
// The upstream owner has confirmed voice_length is recorded in seconds.
const faNumber = value => new Intl.NumberFormat('fa-IR').format(value);

export function voiceDurationSegments(value) {
  if (value === null || value === undefined || value === '') return [];
  const n = Number(value);
  if (!Number.isFinite(n) || n < 0) return [];
  const total = Math.round(n);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const parts = [];
  if (hours) parts.push(faNumber(hours) + ' ساعت');
  if (minutes) parts.push(faNumber(minutes) + ' دقیقه');
  if (seconds || !parts.length) parts.push(faNumber(seconds) + ' ثانیه');
  return parts;
}

export function formatVoiceDuration(value) {
  const parts = voiceDurationSegments(value);
  return parts.length ? parts.join(' و ') : '—';
}


// Source semantics are still provisional: in 297 samples, call_time behaved
// like seconds since Tehran midnight. This is a clock, never audio duration.
// Keep API values unchanged; reject missing/out-of-range/non-integer values.
export function formatSourceCallClock(value) {
  if (value === null || value === undefined || value === '' || typeof value === 'boolean') return '—';
  const n = Number(value);
  if (!Number.isInteger(n) || n < 0 || n >= 86400) return '—';
  const two = part => new Intl.NumberFormat('fa-IR', {
    minimumIntegerDigits:2, useGrouping:false
  }).format(part);
  return two(Math.floor(n/3600)) + ':' + two(Math.floor(n%3600/60));
}

// A source zero is not proof of zero sales. Hide it from call-detail metadata,
// but preserve the raw unverified field and any nonzero value in the API.
export function hasDisplayableDealValue(value) {
  if (value === null || value === undefined || value === '') return false;
  const n = Number(value);
  return Number.isFinite(n) && n !== 0;
}
