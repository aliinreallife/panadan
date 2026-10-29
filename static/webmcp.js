/**
 * Panadan WebMCP — optional browser-tab tools (not remote MCP).
 *
 * The browser's document.modelContext controls discovery. Tools only use
 * same-origin, session-authenticated GET endpoints and never expose tokens,
 * customer identifiers or raw transcripts. Backend RBAC is authoritative.
 */
import { callTypeLabel, callStateLabel } from './labels.js';

const REQUEST_LIMIT = 20;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const FILTER_RE = /^[\p{L}\p{N} _-]{1,60}$/u;
const ERROR_MESSAGE = 'امکان دریافت اطلاعات مجاز وجود ندارد. وضعیت ورود و دسترسی را بررسی کنید.';

const publicCall = row => ({
  id: row.id,
  call_date: row.CALLDATE ?? null,
  agent: row.vw_danix_base_info_users_name ?? null,
  type: row.tellstate ?? null,
  type_fa: callTypeLabel(row.tellstate),
  state: row.aicallinfostate ?? null,
  state_fa: callStateLabel(row.aicallinfostate),
  ai_score: row.possibility_of_sale_ai ?? null,
  voice_length: row.voice_length ?? null
});

function ensureDate(value, name) {
  if (value === undefined || value === null || value === '') return '';
  if (typeof value !== 'string' || !DATE_RE.test(value)) throw new Error(name + ' باید تاریخ میلادی YYYY-MM-DD باشد.');
  const parsed = new Date(value + 'T00:00:00Z');
  if (Number.isNaN(parsed.valueOf()) || parsed.toISOString().slice(0, 10) !== value) {
    throw new Error(name + ' نامعتبر است.');
  }
  return value;
}

function ensureRange(after, before) {
  if (after && before && after > before) throw new Error('تاریخ شروع نباید بعد از تاریخ پایان باشد.');
}

function ensureFilter(value, name) {
  if (value === undefined || value === null || value === '') return '';
  if (typeof value !== 'string' || !FILTER_RE.test(value)) {
    throw new Error(name + ' معتبر نیست.');
  }
  return value;
}

function ensureInteger(value, name, min, max) {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < min || value > max) {
    throw new Error(name + ' خارج از محدوده است.');
  }
  return value;
}

const schemaDate = description => ({type:'string', pattern:'^\\d{4}-\\d{2}-\\d{2}$', description});
const guarded = work => async (input={}, context={}) => {
  try {
    if (!input || typeof input !== 'object' || Array.isArray(input)) {
      throw new Error('پارامترهای ورودی باید یک شیء باشند.');
    }
    return await work(input, context);
  } catch (error) {
    return {error: error?.userMessage || (error?.name === 'ValidationError' ? error.message : ERROR_MESSAGE)};
  }
};
const invalid = message => {
  const error=new Error(message);
  error.name='ValidationError';
  return error;
};
const validate = (fn, ...args) => {
  try {return fn(...args);} catch(error){throw invalid(error.message);}
};

export function createWebMcpTools({ canReadCalls=false, canReadMetrics=false, canReadTranscripts=false, request }) {
  if (typeof request !== 'function') throw new TypeError('request must be a function');
  const tools = [];
  if (canReadMetrics) {
    tools.push({
      name: 'panadan_get_call_metrics',
      description: 'Read aggregate call reporting metrics for the signed-in Panadan user. Counts and averages only; no individual conversations.',
      inputSchema: {
        type:'object', additionalProperties:false,
        properties: {
          after: schemaDate('Optional Gregorian start date, inclusive; use YYYY-MM-DD.'),
          before: schemaDate('Optional Gregorian end date, inclusive; use YYYY-MM-DD.')
        }
      },
      annotations: {readOnlyHint:true, untrustedContentHint:true},
      execute: guarded(async ({after,before}, {signal}={}) => {
        const a=validate(ensureDate,after,'از تاریخ'), b=validate(ensureDate,before,'تا تاریخ');
        validate(ensureRange,a,b);
        const params=new URLSearchParams();
        if(a) params.set('after',a);
        if(b) params.set('before',b);
        const response=await request('/dashboard/metrics'+(params.size?'?'+params:''),signal);
        return {
          total: response.total ?? null,
          sold_out: response.sold_out ?? null,
          average_ai_score: response.avg_ai_score ?? null,
          average_voice_length: response.avg_voice_length ?? null,
          note: 'SoldOut is a reporting classification; not independent proof of payment.'
        };
      })
    });
  }
  if (canReadCalls) {
    tools.push({
      name: 'panadan_find_calls',
      description: 'Find a small page of authorized call reporting records by date, call type or AI status, without customer identifiers or transcripts.',
      inputSchema: {
        type:'object', additionalProperties:false,
        properties: {
          after:schemaDate('Optional Gregorian start date, inclusive.'),
          before:schemaDate('Optional Gregorian end date, inclusive.'),
          call_type:{type:'string',maxLength:60,description:'Raw source call type, such as FollowUp or FirstToch.'},
          state:{type:'string',maxLength:60,description:'Raw source status, such as SoldOut or Unchecked.'},
          limit:{type:'integer',minimum:1,maximum:20,description:'Number of records to retrieve; at most 20.'},
          offset:{type:'integer',minimum:0,maximum:10000,description:'Pagination offset, from zero.'}
        }
      },
      annotations:{readOnlyHint:true,untrustedContentHint:true},
      execute:guarded(async ({after,before,call_type,state,limit=10,offset=0},{signal}={}) => {
        const a=validate(ensureDate,after,'از تاریخ'),b=validate(ensureDate,before,'تا تاریخ');
        validate(ensureRange,a,b);
        const type=validate(ensureFilter,call_type,'نوع تماس');
        const status=validate(ensureFilter,state,'وضعیت تماس');
        const take=validate(ensureInteger,limit,'تعداد',1,REQUEST_LIMIT);
        const skip=validate(ensureInteger,offset,'شروع',0,10000);
        const params=new URLSearchParams({limit:String(take),offset:String(skip)});
        if(a)params.set('after',a);
        if(b)params.set('before',b);
        if(type)params.set('call_type',type);
        if(status)params.set('state',status);
        const response=await request('/dashboard/data?'+params,signal);
        return {
          items:(Array.isArray(response.items)?response.items.slice(0,take):[]).map(publicCall),
          limit:take, offset:skip
        };
      })
    });
    tools.push({
      name:'panadan_get_call_overview',
      description:'Read approved high-level metadata of one call by ID. Does not return customer details, summaries, transcripts or recommendations.',
      inputSchema:{
        type:'object',additionalProperties:false,
        properties:{call_id:{type:'integer',minimum:1,maximum:2147483647,description:'Numeric Panadan call record ID.'}},
        required:['call_id']
      },
      annotations:{readOnlyHint:true,untrustedContentHint:true},
      execute:guarded(async ({call_id},{signal}={})=>{
        const id=validate(ensureInteger,call_id,'شناسه تماس',1,2147483647);
        const response=await request('/dashboard/overview/'+id,signal);
        return publicCall(response);
      })
    });
  }
  if (canReadCalls && canReadTranscripts) {
    tools.push({
      name: 'panadan_get_redacted_transcript',
      description: 'Read one redacted excerpt of a call transcript with explicit user permission. May contain private spoken information. Use only when the user asks for conversation analysis.',
      inputSchema:{
        type:'object',additionalProperties:false,
        properties:{
          call_id:{type:'integer',minimum:1,maximum:2147483647},
          offset:{type:'integer',minimum:0,description:'Start of the next chunk; use next_offset from previous response.'}
        },
        required:['call_id']
      },
      annotations:{readOnlyHint:true,untrustedContentHint:true},
      execute:guarded(async ({call_id,offset=0},{signal}={})=>{
        const id=validate(ensureInteger,call_id,'شناسه تماس',1,2147483647);
        const start=validate(ensureInteger,offset,'شروع متن',0,2147483647);
        const response=await request('/dashboard/ai/transcript/'+id+'?offset='+start,signal);
        return {
          call_id:response.call_id,
          text:response.text,
          truncated:Boolean(response.truncated),
          has_more:Boolean(response.has_more),
          next_offset:response.next_offset,
          offset:response.offset,
          source_chars:response.source_chars,
          presentation:response.presentation,
          privacy_notice:response.privacy_notice
        };
      })
    });
  }
  return tools;
}

/** Return null on browsers without WebMCP. No polyfill or external script. */
export async function registerPanadanWebMcp({page=globalThis.document, fetchImpl=globalThis.fetch}={}) {
  if (!page || typeof page.modelContext?.registerTool !== 'function') return null;
  const canReadCalls=Boolean(page.getElementById('rows'));
  const canReadMetrics=Boolean(page.getElementById('metric-total'));
  const canReadTranscripts=Boolean(page.getElementById('webmcp-transcript-permission'));
  if (!canReadCalls && !canReadMetrics) return null;
  const fetchSameOrigin=async (url,signal) => {
    const response=await fetchImpl(url,{method:'GET',credentials:'same-origin',cache:'no-store',signal});
    if (!response.ok) throw new Error('Not authorized or unavailable');
    return response.json();
  };
  const tools=createWebMcpTools({canReadCalls,canReadMetrics,canReadTranscripts,request:fetchSameOrigin});
  const controller=new AbortController();
  try {
    for (const tool of tools) {
      await page.modelContext.registerTool(tool,{signal:controller.signal});
    }
  } catch {
    controller.abort();
    return null;
  }
  page.defaultView?.addEventListener?.('pagehide',()=>controller.abort(),{once:true});
  return {controller,names:tools.map(tool=>tool.name)};
}
