// Optional maintainer capture against a fresh, dedicated headless browser profile.
// Node >=22 supplies fetch/WebSocket. This is not a demo/runtime dependency.
import fs from 'node:fs';
import path from 'node:path';

const endpoint = 'http://127.0.0.1:9239';
let pages = [];
for (let i = 0; i < 40; i++) {
  try {
    pages = await (await fetch(endpoint + '/json/list')).json();
    if (pages.some(p => p.type === 'page' && p.url.startsWith('http://127.0.0.1:8501'))) break;
  } catch {}
  await new Promise(resolve => setTimeout(resolve, 250));
}
const target = pages.find(p => p.type === 'page' && p.url.startsWith('http://127.0.0.1:8501'));
if (!target) throw new Error('Dedicated localhost demo page unavailable');
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {ws.onopen = resolve; ws.onerror = reject;});
let serial = 0;
const pending = new Map();
ws.onmessage = message => {
  const response = JSON.parse(message.data);
  if (!response.id) return;
  const waiter = pending.get(response.id);
  pending.delete(response.id);
  if (response.error) waiter?.reject(new Error(JSON.stringify(response.error)));
  else waiter?.resolve(response.result);
};
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++serial;
  pending.set(id, {resolve, reject});
  ws.send(JSON.stringify({id, method, params}));
});
const evaluate = async expression => (await send('Runtime.evaluate', {expression, returnByValue: true})).result.value;
const waitText = async text => {
  for (let i = 0; i < 80; i++) {
    if (await evaluate(`document.body.innerText.includes(${JSON.stringify(text)})`)) return;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error('Expected demo state missing: ' + text);
};
const clickText = async (selector, text) => {
  const point = await evaluate(`(() => {const e=Array.from(document.querySelectorAll(${JSON.stringify(selector)})).find(x=>x.innerText.includes(${JSON.stringify(text)})); if(!e) throw new Error('Missing control'); e.scrollIntoView({block:'center'}); const r=e.getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2};})()`);
  await send('Input.dispatchMouseEvent', {type:'mousePressed',button:'left',clickCount:1,...point});
  await send('Input.dispatchMouseEvent', {type:'mouseReleased',button:'left',clickCount:1,...point});
};
await send('Page.enable');
await send('Emulation.setDeviceMetricsOverride', {width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false});
await waitText('Make agent behavior inspectable.');
await clickText('[role=tab]', 'Trace explorer');
await waitText('How many artists are in the database?');
const directory = path.resolve('reports/screenshots');
fs.mkdirSync(directory, {recursive: true});
const capture = async name => {
  const result = await send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: false});
  fs.writeFileSync(path.join(directory, name), Buffer.from(result.data, 'base64'));
};
await evaluate('window.scrollTo(0,0)');
await capture('trace-explorer.png');
await clickText('[role=tab]', 'Study & checks');
await waitText('Evidence before claims');
await clickText('button', 'Run the 20-task offline regression');
await waitText('Engineering regression gate passed.');
await capture('offline-checks.png');
console.log(JSON.stringify({title: await evaluate('document.title'), browser_regression_button: 'passed', screenshots: ['trace-explorer.png', 'offline-checks.png']}));
// This Browser.close targets only the dedicated headless instance on port 9239.
ws.send(JSON.stringify({id: ++serial, method: 'Browser.close'}));
setTimeout(() => process.exit(0), 500);
