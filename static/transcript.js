/**
 * Lossless-display companion for potentially messy speech-to-text transcripts.
 * `raw` is NEVER modified or persisted; parsing is strictly presentational.
 * Supports actual or escaped newlines, colon/split speaker labels and multiline turns.
 */
const SPEAKER = /^(مشتری|اپراتور|کارشناس|مشاور|پشتیبان|تماس[\u200c\s]*گیرنده|گوینده\s*[۱۲12])(?:\s*[:：]\s*(.*)|\s*)$/u;
const SPEAKER_NAME = {
  'مشتری': 'مشتری', 'اپراتور': 'اپراتور', 'کارشناس': 'اپراتور',
  'مشاور': 'اپراتور', 'پشتیبان': 'اپراتور',
};

function matchSpeaker(line) {
  const match = line.trim().match(SPEAKER);
  if (!match) return null;
  const rawLabel = match[1].replace(/[\u200c\s]+/g, ' ').trim();
  let speaker = SPEAKER_NAME[rawLabel];
  if (!speaker) speaker = rawLabel.startsWith('گوینده') ? rawLabel : 'مشتری';
  return { speaker, body: match[2] ?? '' };
}

/** @returns {{turns: Array<{speaker:string,text:string}>, raw:string, normalized:string, warnings:string[], stats:object}} */
export function parseTranscript(input) {
  const raw = typeof input === 'string' ? input : '';
  // Converts only explicit escaped newline boundaries for display; keeps original raw intact.
  const normalized = raw.replace(/\\r\\n|\\n|\\r/g, '\n').replace(/\r\n?|\u2028|\u2029/g, '\n').replace(/\\(?=\n)/g, '');
  const lines = normalized.split('\n');
  const turns = [];
  let speaker = 'نامشخص';
  let body = [];
  let pending = false;
  let emptyLabels = 0;
  let labelsFound = 0;
  let unattributed = 0;
  const push = () => {
    const text = body.join('\n').trim();
    if (text) turns.push({ speaker, text });
    else if (pending) emptyLabels += 1;
    body = [];
    pending = false;
  };
  for (const line of lines) {
    const hit = matchSpeaker(line);
    if (hit) {
      push();
      speaker = hit.speaker;
      labelsFound += 1;
      pending = true;
      if (hit.body.trim()) body.push(hit.body.trim());
    } else {
      if (line.trim() && !pending && speaker === 'نامشخص') unattributed += 1;
      // Don't lose multiline speech or narration without labels.
      body.push(line);
    }
  }
  push();
  const warnings = [];
  if (emptyLabels) warnings.push(`${emptyLabels.toLocaleString('fa-IR')} برچسب بدون گفتار نادیده گرفته شد`);
  if (unattributed || !labelsFound) warnings.push('بخشی از گفتار گویندهٔ مشخص ندارد');
  return { turns, raw, normalized, warnings, stats: { labelsFound, emptyLabels, unattributed, turns: turns.length } };
}
