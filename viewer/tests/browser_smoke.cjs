// Usage: node viewer/tests/browser_smoke.cjs <playwright-module> [chrome-path] [fixture] [batch ...]
const { chromium } = require(process.argv[2] || 'playwright');
const { spawn, execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '../..');
const python = process.env.HWPX_PYTHON || 'python';
const folder = path.join(root, 'output', `browser-${Date.now()}`);
fs.mkdirSync(folder, {recursive:true});
const file = path.join(folder, 'live.hwpx');
function cli(args) {
  return JSON.parse(execFileSync(python, ['-m', 'hwpx_cli', ...args], {cwd:root,encoding:'utf8'}));
}
const fixture = process.argv[4];
const batches = process.argv.slice(5);
if (fixture) {
  cli(['copy',fixture,'--output',file]);
} else {
  cli(['create','--output',file]);
  cli(['text','insert',file,'--target','Contents/section0.xml#0','--start','0','--text','HWPX CLI 실시간 편집 테스트','--in-place']);
}
const viewer = spawn(python, ['-m','viewer.server',file], {cwd:root,stdio:['ignore','pipe','pipe']});
let stderr = '';
viewer.stderr.on('data', chunk => { stderr += chunk; });
const urlPromise = new Promise((resolve,reject) => {
  let output = '';
  viewer.stdout.on('data', chunk => {
    output += chunk;
    const line = output.split('\n').find(line => line.startsWith('{'));
    if (line) { try { resolve(JSON.parse(line).viewer); } catch {} }
  });
  viewer.on('exit',code => reject(Error(`Viewer exited ${code}: ${stderr}`)));
  setTimeout(() => reject(Error(`Viewer startup timeout: ${stderr}`)), 20000).unref();
});
(async () => {
  let browser;
  const errors = [];
  try {
    const url = await urlPromise;
    browser = await chromium.launch({headless:true,executablePath:process.argv[3] || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
    const page = await browser.newPage({viewport:{width:1280,height:1000}});
    page.on('pageerror',e => errors.push(String(e)));
    page.on('console',m => { if(m.type()==='error') errors.push(m.text()); });
    await page.goto(url);
    try {
      await page.waitForFunction(() => window.hwpxViewerState, undefined, {timeout:60000});
    } catch (error) {
      await page.screenshot({path:path.join(folder,'failure.png'),fullPage:true});
      console.error(JSON.stringify({status:await page.locator('#status').textContent(),errors,folder},null,2));
      throw error;
    }
    const before = await page.evaluate(() => window.hwpxViewerState);
    const pixels = await page.evaluate(() => {
      const c = document.querySelector('canvas');
      const d = c.getContext('2d').getImageData(0,0,c.width,c.height).data;
      let ink=0; for(let i=0;i<d.length;i+=4) if(d[i+3] && (d[i]<240 || d[i+1]<240 || d[i+2]<240)) ink++;
      return {width:c.width,height:c.height,ink};
    });
    assert(pixels.ink > 100, `No visible document content: ${JSON.stringify(pixels)}`);
    await page.screenshot({path:path.join(folder,'before.png'),fullPage:true});
    const replacement = fixture
      ? ['--target','Contents/section0.xml#0','--text','40초','--with','45초']
      : ['--text','실시간','--with','자동 갱신 성공'];
    const stages = [];
    async function capture(name) {
      const state = await page.evaluate(async () => {
        const { version, count } = window.hwpxViewerState;
        const engine = await import('./rhwp/rhwp.js');
        const bytes = new Uint8Array(await (await fetch('api/document/' + version)).arrayBuffer());
        const document = new engine.HwpDocument(bytes);
        try {
          return Array.from({length: count}, (_, index) => {
            const svg = new DOMParser().parseFromString(document.renderPageSvg(index), 'image/svg+xml');
            const { behind, front } = JSON.parse(document.getPageOverlayImages(index));
            return {
              text: [...svg.querySelectorAll('text')].map(node => node.textContent),
              flow: JSON.parse(document.getPageFlowImageOps(index)).images,
              overlay: [...behind, ...front].map(({bbox, wrap}) => ({bbox, wrap})),
              redStrokes: svg.querySelectorAll('[stroke="#b52222" i]').length,
            };
          });
        } finally { document.free(); }
      });
      for (let i = 1; i <= state.length; i++) {
        await page.locator('#page').fill(String(i));
        await page.locator('#page').dispatchEvent('change');
        assert.equal(await page.locator('canvas').getAttribute('aria-label'), `문서 ${i} 페이지`);
        await page.screenshot({path:path.join(folder, name + '-p' + i + '.png'), fullPage:true});
      }
      await page.locator('#page').fill('1');
      await page.locator('#page').dispatchEvent('change');
      fs.copyFileSync(file, path.join(folder, name + '.hwpx'));
      stages.push({name, version: (await page.evaluate(() => window.hwpxViewerState)).version, pages:state});
    }
    let result;
    if (batches.length) {
      await capture('baseline');
      for (const batch of batches) {
        result = cli(['apply',file,'--batch',batch,'--in-place']);
        await page.waitForFunction(version => window.hwpxViewerState?.version === version,result.version,{timeout:60000});
        await capture(path.basename(batch, '.json'));
      }
    } else {
      result = cli(['text','replace',file,...replacement,'--in-place']);
      await page.waitForFunction(version => window.hwpxViewerState?.version === version,result.version,{timeout:60000});
    }
    assert.notEqual(before.version,result.version);
    await page.screenshot({path:path.join(folder,'after.png'),fullPage:true});
    const current = fs.readFileSync(file);
    const damaged = path.join(folder,'valid.hwpx');
    fs.writeFileSync(damaged,current);
    fs.writeFileSync(file,Buffer.from('incomplete'));
    await page.waitForFunction(() => document.querySelector('#status').classList.contains('error'));
    fs.writeFileSync(file,current);
    await page.waitForFunction(() => !document.querySelector('#status').classList.contains('error'));
    assert.equal(crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'),result.version);
    await page.locator('#zoom').selectOption('1.25');
    const report = {before,after:await page.evaluate(() => window.hwpxViewerState),pixels,errors,folder,stages};
    fs.writeFileSync(path.join(folder,'report.json'),JSON.stringify(report,null,2));
    assert.equal(errors.filter(e => !e.includes('favicon')).length,0,errors.join('\n'));
    console.log(JSON.stringify({...report,stages:stages.map(stage => ({name:stage.name, pages:stage.pages.length}))},null,2));
  } finally {
    await browser?.close();
    viewer.kill();
  }
})().catch(e => { console.error(e); process.exitCode=1; });
