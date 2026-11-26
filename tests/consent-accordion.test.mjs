import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import vm from 'node:vm';
const policy=readFileSync(new URL('../static/mcp-apps.js',import.meta.url),'utf8');
const ui=readFileSync(new URL('../static/consent-accordion.js',import.meta.url),'utf8');
function control(value,checked=false){
 const row={hidden:true,classList:{toggle(){}}},listeners={};
 return {value,checked,disabled:false,dataset:{},listeners,
  closest(){return row;},focus(){this.focused=true;},
  addEventListener(type,fn){(listeners[type]??=[]).push(fn);},
  dispatchEvent(e){for(const fn of listeners[e.type]??[])fn(e);},
  change(checked){this.checked=checked;this.dispatchEvent({type:'change'});}
 };
}
test('three groups share one submitted field and do not auto-grant transcripts',()=>{
 const call=control('calls:read',true),metrics=control('metrics:read',true),transcript=control('calls:transcript:read');
 const id=control('id',true),date=control('CALLDATE'),text=control('transcription');
 const mirror=control('');mirror.dataset.sharedField='id';
 const caps=[call,metrics,transcript],fields=[id,date,text],status={textContent:''};
 const groups=caps.map((cap,i)=>({dataset:{consentGroup:cap.value},classList:{toggle(){}},
   count:{textContent:''},querySelector(){return this.count;},
   querySelectorAll(){return [[id,date],[mirror],[text]][i];}}));
 const listeners={};
 const form={querySelectorAll(q){return {
  'input[name="capabilities"]':caps,'input[name="fields"]':fields,
  '[data-consent-group]':groups,'[data-shared-field]':[mirror]}[q];},
  querySelector(){return status;},addEventListener(k,fn){listeners[k]=fn;}};
 const document={querySelectorAll(){return [form];}};
 const ctx={document,Event:class{constructor(type){this.type=type;}}};
 vm.runInNewContext(policy,ctx);vm.runInNewContext(ui,ctx);
 assert.equal(mirror.checked,true);assert.equal(text.checked,false);assert.equal(text.disabled,true);
 mirror.change(false);assert.equal(id.checked,false);
 id.change(true);assert.equal(mirror.checked,true);
 transcript.change(true);assert.equal(text.checked,false);
 text.change(true);id.change(false);
 assert.match(status.textContent,/شناسه تماس/);
 let prevented=false;listeners.submit({preventDefault(){prevented=true;}});
 assert.equal(prevented,true);assert.equal(groups[0].open,true);
 call.change(false);
 assert.equal(transcript.checked,false);assert.equal(text.checked,false);assert.equal(text.disabled,true);
 assert.equal(mirror.disabled,false);
});
