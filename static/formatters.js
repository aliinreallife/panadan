// Presentation-only formatters. Reporting API values stay unchanged.
// The upstream owner has confirmed voice_length is recorded in seconds.
const faNumber = value => new Intl.NumberFormat('fa-IR').format(value);

export function formatVoiceDuration(value) {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  if (!Number.isFinite(n) || n < 0) return '—';
  // Averages can be fractional seconds; round once, for display only.
  const total = Math.round(n);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const parts = [];
  if (hours) parts.push(faNumber(hours) + ' ساعت');
  if (minutes) parts.push(faNumber(minutes) + ' دقیقه');
  if (seconds || !parts.length) parts.push(faNumber(seconds) + ' ثانیه');
  return parts.join(' و ');
}
