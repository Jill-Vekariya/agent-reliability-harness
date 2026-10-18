// Verify only the explicitly supplied project demo in a dedicated browser profile.
// Start a fresh headless Chromium/Edge instance on port 9239 before this script.
import fs from 'node:fs';
import path from 'node:path';
const targetUrl = process.env.VERIFY_PUBLIC_DEMO_URL;
if (!targetUrl || !/^https?:\/\//.test(targetUrl)) throw new Error('Explicit demo URL required');
let target;
for (let i = 0; i < 60; i++) {
  try {
    const pages = await (await fetch('http://127.0.0.1:9239/json/list')).json();
    target = pages.find(p => p.type === 'page' && p.url.startsWith(targetUrl));
    if (target) break;
  } catch {}
  await new Promise(resolve => setTimeout(resolve, 250));
}
if (!target) throw new Error('Dedicated project page unavailable');
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
let serial = 0;
const pending = new Map();
const errors = [];
ws.onmessage = message => {
  const response = JSON.parse(message.data);
  if (response.method === 'Runtime.exceptionThrown') errors.push(response.params.exceptionDetails.text);
  if (!response.id) return;
  const waiter = pending.get(response.id); pending.delete(response.id);
  if (response.error) waiter?.reject(new Error(JSON.stringify(response.error)));
  else waiter?.resolve(response.result);
};
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++serial; pending.set(id, {resolve, reject}); ws.send(JSON.stringify({id, method, params}));
});
const evaluate = async expression => {
  const response = await send('Runtime.evaluate', {expression, returnByValue: true});
  if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails));
  return response.result.value;
};
const assert = (condition, message) => { if (!condition) throw new Error(message); };
const click = async id => {
  const point = await evaluate(`(() => { const e=document.querySelector('[data-case="${id}"]'); e.scrollIntoView({block:'center'}); const r=e.getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2}; })()`);
  await send('Input.dispatchMouseEvent', {type:'mousePressed',button:'left',clickCount:1,...point});
  await send('Input.dispatchMouseEvent', {type:'mouseReleased',button:'left',clickCount:1,...point});
};
await send('Page.enable'); await send('Runtime.enable');
for (let i = 0; i < 60; i++) {
  if (await evaluate('document.querySelectorAll(".case-button").length === 4')) break;
  await new Promise(resolve => setTimeout(resolve, 250));
}
assert(await evaluate('document.querySelectorAll(".case-button").length === 4'), 'Trace controls did not render');
assert(await evaluate('document.querySelector("#answer").innerText.includes("275")'), 'Supported count missing');
await click('q002');
assert(await evaluate('document.querySelector("#steps").innerText.includes("InventedName")'), 'Schema failure missing');
assert(await evaluate('document.querySelector("#answer").innerText.includes("NO SUPPORTED")'), 'Failed trace received answer');
await click('s001');
assert(await evaluate('document.querySelector("#steps").innerText.includes("BLOCKED")'), 'Blocked-query state missing');
assert(await evaluate('document.querySelector("#case-context").innerText.includes("not measured")'), 'Synthetic qualification missing');
await click('recovery');
assert(await evaluate('document.querySelector("#answer").innerText.includes("A Cor Do Som")'), 'Recovery result missing');
await click('q001');
await send('Emulation.setDeviceMetricsOverride', {width:1440,height:1100,deviceScaleFactor:1,mobile:false});
await evaluate('window.scrollTo(0,0)');
const directory = path.resolve('reports/screenshots'); fs.mkdirSync(directory, {recursive:true});
const screenshot = await send('Page.captureScreenshot', {format:'png',captureBeyondViewport:false});
fs.writeFileSync(path.join(directory,'public-demo.png'), Buffer.from(screenshot.data,'base64'));
await send('Emulation.setDeviceMetricsOverride', {width:375,height:900,deviceScaleFactor:1,mobile:true});
assert(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile horizontal overflow');
assert(errors.length === 0, 'Browser exception: ' + errors.join(', '));
const evidence = {schema_version:1,url:targetUrl,captured_at:new Date().toISOString(),four_case_controls:'passed',supported_result:'passed',schema_failure:'passed',blocked_query:'passed',scripted_recovery:'passed',mobile_width:375,horizontal_overflow:false,browser_exceptions:errors,screenshot:'reports/screenshots/public-demo.png'};
fs.writeFileSync(path.resolve('reports/public-demo-browser.json'),JSON.stringify(evidence,null,2)+'\n');
console.log(JSON.stringify(evidence));
ws.send(JSON.stringify({id:++serial,method:'Browser.close'}));
setTimeout(() => process.exit(0),500);
