import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import vm from 'node:vm';
const source=readFileSync(new URL('../static/connect-guide.js',import.meta.url),'utf8');
const names=['chatgpt','claude','gemini'];
function element(name,key){
 const attributes={},listeners={};
 return {id:key==='guideTab'?'tab-'+name:name,dataset:{[key]:name},attributes,listeners,
  setAttribute(k,v){attributes[k]=v;},addEventListener(k,v){listeners[k]=v;},focus(){this.focused=true;}};
}
test('assistant guide shows exactly one panel and supports RTL keyboard selection and deep links',()=>{
 const tabs=names.map(n=>element(n,'guideTab'));
 const panels=names.map(n=>element(n,'guidePanel'));
 const list={...element('',''),querySelectorAll(){return tabs;}};
 const location={hash:'#claude'};
 const events={};
 const document={querySelector(){return list;},querySelectorAll(q){return q==='[data-guide-panel]'?panels:[];}};
 vm.runInNewContext(source,{document,location,history:{replaceState(_a,_b,hash){location.hash=hash;}},window:{addEventListener(k,v){events[k]=v;}}});
 assert.deepEqual(panels.map(p=>p.hidden),[true,false,true]);
 assert.equal(tabs[1].attributes['aria-selected'],'true');
 assert.equal(tabs[1].tabIndex,0);
 tabs[1].listeners.keydown({key:'ArrowLeft',preventDefault(){}});
 assert.deepEqual(panels.map(p=>p.hidden),[true,true,false]);
 assert.equal(tabs[2].focused,true);
 assert.equal(location.hash,'#gemini');
 tabs[0].listeners.click({preventDefault(){}});
 assert.deepEqual(panels.map(p=>p.hidden),[false,true,true]);
 location.hash='#unknown';events.hashchange();
 assert.equal(panels[0].hidden,false);
});
test('copy controls use the exact configured field value and announce success',async()=>{
 let copied;
 const status={textContent:''};
 const button=element('','');button.dataset.guideCopy='https://example.invalid/mcp/';
 button.textContent='کپی';button.closest=()=>({querySelector:()=>status});
 vm.runInNewContext(source,{document:{querySelector:()=>null,querySelectorAll:()=>[button]},
  navigator:{clipboard:{writeText:async v=>{copied=v;}}},clearTimeout(){},setTimeout(){return 1;}});
 await button.listeners.click();
 assert.equal(copied,button.dataset.guideCopy);
 assert.equal(status.textContent,'کپی شد.');
});
