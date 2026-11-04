/**
 * Lossless-display companion for potentially messy speech-to-text transcripts.
 * \`raw\` is NEVER modified or persisted; parsing is strictly presentational.
 * Supports newline-delimited speaker labels and dense single-paragraph dialogue.
 * Dense paragraphs are heuristic and always retain the exact Raw tab.
 */
const SPEAKER = /^(مشتری|اپراتور|اپاتور|کارشناس|مشاور|پشتیبان|تماس[\u200c\s]*گیرنده|گوینده\s*[۱۲12])(?:\s*[:：.،؟؛!]\s*(.*)|\s*)$/u;
const SPEAKER_NAME = {
  'مشتری': 'مشتری', 'اپراتور': 'اپراتور', 'اپاتور': 'اپراتور', 'کارشناس': 'اپراتور',
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

/**
 * A dense one-line STT transcript can look like:
 * "مشتری اپراتور سلام مشتری سلام اپراتور. بفرمایید مشتری؟ بله"
 * A single bare "مشتری" in normal prose is NOT enough to infer a turn.
 * Require a paragraph that starts with a speaker label and has >=3 candidate
 * labels (or >=2 with explicit role punctuation), with both role types.
 */
const INLINE_ROLE = /(?<![\p{L}\p{N}\u200c])(مشتری|اپراتور|اپاتور)(?:([:：.،؟؛!])|(?=\s|$))/gu;
function inlineSpeakers(line) {
  const matches = [...line.matchAll(INLINE_ROLE)].map(hit => ({
    index: hit.index,
    end: hit.index + hit[0].length,
    speaker: SPEAKER_NAME[hit[1]] || hit[1],
    explicit: Boolean(hit[2]),
  }));
  if (!matches.length || line.slice(0, matches[0].index).trim()) return null;
  if (new Set(matches.map(hit => hit.speaker)).size < 2) return null;
  if (matches.length < 3 && matches.filter(hit => hit.explicit).length < 1) return null;
  return matches;
}

/** @returns {{turns: Array<{speaker:string,text:string}>, raw:string, normalized:string, warnings:string[], stats:object}} */
export function parseTranscript(input) {
  const raw = typeof input === 'string' ? input : '';
  // Display normalization ONLY. The raw transcript is returned byte-for-byte.
  const normalized = raw.replace(/\\r\\n|\\n|\\r/g, '\n').replace(/\r\n?|\u2028|\u2029/g, '\n').replace(/\\(?=\n)/g, '');
  const lines = normalized.split('\n');
  const turns = [];
  let speaker = 'نامشخص';
  let body = [];
  let pending = false;
  let emptyLabels = 0;
  let labelsFound = 0;
  let unattributed = 0;
  let inlineLines = 0;
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
      continue;
    }
    const embedded = inlineSpeakers(line);
    if (embedded) {
      inlineLines += 1;
      let offset = 0;
      for (const marker of embedded) {
        const speech = line.slice(offset, marker.index).trim();
        if (speech) body.push(speech);
        push();
        speaker = marker.speaker;
        labelsFound += 1;
        pending = true;
        offset = marker.end;
      }
      const trailing = line.slice(offset).trim();
      if (trailing) body.push(trailing);
      continue;
    }
    if (line.trim() && !pending && speaker === 'نامشخص') unattributed += 1;
    // Don't discard any multiline speech or narrator text without labels.
    body.push(line);
  }
  push();
  const warnings = [];
  if (emptyLabels) warnings.push(\`\${emptyLabels.toLocaleString('fa-IR')} برچسب بدون گفتار نادیده گرفته شد\`);
  if (inlineLines) warnings.push('تفکیک گویندگان در متن یک‌خطی احتمالی است؛ با متن خام مقایسه کنید');
  if (unattributed || !labelsFound) warnings.push('بخشی از گفتار گویندهٔ مشخص ندارد');
  return {
    turns, raw, normalized, warnings,
    stats: { labelsFound, emptyLabels, unattributed, inlineLines, turns: turns.length },
  };
}
