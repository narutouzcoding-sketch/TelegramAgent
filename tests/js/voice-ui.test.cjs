const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const {Blob}=require('node:buffer');
const source=fs.readFileSync(require('node:path').join(__dirname,'../../telegram_agent/panel_web/voice-ui.js'),'utf8');
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function setup(deferred=false){
  let release,stops=0,opens=0,uploaded='';
  const nodes=new Map();
  const node=s=>{if(!nodes.has(s))nodes.set(s,{value:'',textContent:'',hidden:false,disabled:false,files:[],add(){},removeAttribute(){}});return nodes.get(s);};
  const form={isConnected:true,querySelector:node};
  const stream={getTracks:()=>[{stop(){stops++;}}]};
  class Recorder{
    static isTypeSupported(){return true;}
    constructor(){this.state='inactive';this.mimeType='audio/webm';}
    start(){this.state='recording';}
    stop(){this.state='inactive';queueMicrotask(()=>{this.ondataavailable({data:new Blob(['MICROPHONE'])});this.onstop();});}
  }
  const context={window:{MediaRecorder:Recorder},MediaRecorder:Recorder,navigator:{mediaDevices:{getUserMedia:()=>{opens++;return deferred?new Promise(r=>release=()=>r(stream)):Promise.resolve(stream);}}},Blob,URL:{createObjectURL:()=> 'blob:qa',revokeObjectURL(){}},setTimeout:()=>1,clearTimeout(){},Option:class{},fetch:async(url,opts)=>{uploaded=await opts.body.text();return {ok:true,json:async()=>({id:'a'.repeat(32),label:'Saved',duration:1})};}};
  vm.runInNewContext(source,context);
  const api=context.window.AgentVoice;
  api.bind(form,{csrf:()=> 'qa',saved(){}});
  return {api,node,form,release:()=>release(),stats:()=>({stops,opens,uploaded})};
}
(async()=>{
  // A selected file must win over a recorder's asynchronous onstop callback.
  let t=setup();await t.node('#voice-record').onclick();
  t.node('#voice-file').onchange({target:{files:[new Blob(['SELECTED_FILE'],{type:'audio/wav'})]}});
  await flush();await t.node('#voice-save').onclick();
  assert.equal(t.stats().uploaded,'SELECTED_FILE');
  assert.ok(t.stats().stops>0);

  // Leaving/logging out while permission is pending cannot activate a hidden mic.
  t=setup(true);const pending=t.node('#voice-record').onclick();
  t.api.cleanup(true);t.release();await pending;
  assert.ok(t.stats().stops>0);
  assert.equal(t.stats().uploaded,'');

  // A second click while requesting permission cannot open a second stream.
  t=setup(true);const first=t.node('#voice-record').onclick();
  await t.node('#voice-record').onclick();t.release();await first;
  assert.equal(t.stats().opens,1);t.api.stop();await flush();
  assert.ok(t.stats().stops>0);

  // A late onstop after logout cannot resurrect a previous user's draft.
  t=setup();await t.node('#voice-record').onclick();t.api.cleanup(true);await flush();
  t.api.bind(t.form,{csrf:()=> 'qa',saved(){}});
  assert.equal(t.node('#voice-save').disabled,true);
  // Switching away from voice mode while permission is pending also cancels capture.
  t=setup(true);const waiting=t.node('#voice-record').onclick();
  t.api.cancel();t.release();await waiting;
  assert.ok(t.stats().stops>0);
  console.log('5 microphone lifecycle scenarios passed (mock devices, no real microphone/network).');
})().catch(error=>{console.error(error);process.exitCode=1;});
