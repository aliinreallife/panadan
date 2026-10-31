// A phone link is a user-initiated action only. No dialing occurs automatically.
// Use the source text field customertell: numeric tellnum can lose leading zeros.
// Fail closed for multiple numbers, extensions, suspicious characters or URLs.
export function dialablePhone(value) {
  if (typeof value !== 'string') return null;
  const digits = value.trim()
    .replace(/[۰-۹]/g, d => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))
    .replace(/[٠-٩]/g, d => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)));
  // A single + is permitted only at the start; spaces, dots, hyphens and
  // parentheses are presentation separators, never control characters.
  if (!/^\+?[0-9][0-9 ().-]*$/.test(digits)) return null;
  const normalized = digits.replace(/[ ().-]/g, '');
  if (!/^\+?[0-9]{7,15}$/.test(normalized)) return null;
  if (!/[1-9]/.test(normalized)) return null;
  return 'tel:' + normalized;
}
