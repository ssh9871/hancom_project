const {chromium}=require(process.argv[2]||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const root=path.resolve(__dirname,'../..');
const folder=path.join(root,'output',`render-cases-${Date.now()}`);fs.mkdirSync(folder,{recursive:true});
const python=process.env.HWPX_PYTHON||'python';
const server=spawn(python,[path.join(__dirname,'render_cases.py'),folder],{cwd:root,stdio:['ignore','pipe','pipe']});
let err='';server.stderr.on('data',d=>err+=d);
const cases=new Promise((resolve,reject)=>{let data='';server.stdout.on('data',d=>{data+=d;try{resolve(JSON.parse(data.trim()))}catch{}});server.on('exit',c=>reject(Error(`Server exit ${c}: ${err}`)));});
(async()=>{
 let browser;
 try{
  const urls=await cases;browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const reports=[];
  for(const test of urls){
   const page=await browser.newPage({viewport:{width:1280,height:1000}});const errors=[];
   page.on('pageerror',e=>errors.push(String(e)));
   await page.goto(test.url);
   await page.waitForFunction(()=>window.hwpxViewerState||document.querySelector('#status').classList.contains('error'),undefined,{timeout:60000});
   const state=await page.evaluate(()=>window.hwpxViewerState);const status=await page.locator('#status').textContent();
   if(test.name==='objects'){
     const blue=await page.evaluate(()=>{const c=document.querySelector('canvas');const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let n=0;for(let i=0;i<d.length;i+=4)if(d[i]>=35&&d[i]<=50&&d[i+1]>=100&&d[i+1]<=120&&d[i+2]>=175&&d[i+2]<=200)n++;return n;});
     if(blue<=100){
       await page.screenshot({path:path.join(folder,'objects-failure.png'),fullPage:true});
       const diagnostic=await page.evaluate(async url=>{const e=await import(new URL('rhwp/rhwp.js',url));const s=await(await fetch(new URL('api/state',url))).json();const b=new Uint8Array(await(await fetch(new URL('api/document/'+s.version,url))).arrayBuffer());const d=new e.HwpDocument(b);try{return {keys:d.getPageSourceImageKeys(0),flow:d.getPageFlowImageOps(0),info:d.getDocumentInfo()};}finally{d.free();}},test.url);
       console.error(JSON.stringify({folder,diagnostic},null,2));
     }
     assert(blue>100,`Embedded picture not visible: ${blue}`);
   }
   await page.screenshot({path:path.join(folder,test.name+'.png'),fullPage:true});
   assert(state,`${test.name}: ${status}; ${errors}`);assert.equal(state.version,test.version);
   const read=await page.evaluate(async({url,encrypted})=>{
     const engine=await import(new URL('rhwp/rhwp.js',url));
     const state=await(await fetch(new URL('api/state',url))).json();
     const bytes=new Uint8Array(await(await fetch(new URL('api/document/'+state.version,url))).arrayBuffer());
     const d=encrypted?engine.HwpDocument.openWithPassword(bytes,'test-only-password'):new engine.HwpDocument(bytes);
     try{return {text:d.getTextFileText(),pages:d.pageCount()};}finally{d.free();}
   },{url:test.url,encrypted:test.name==='encrypted'});
   assert.equal(errors.length,0,errors.join('\n'));
   if(test.name==='pagination')assert(read.pages>1,`Missing pagination: ${read.pages}`);
   if(test.name==='encrypted')assert(read.text.includes('암호 문서'),read.text);
   reports.push({name:test.name,state,text:read.text.slice(0,160),pages:read.pages,errors});
   await page.close();
  }
  fs.writeFileSync(path.join(folder,'report.json'),JSON.stringify(reports,null,2));console.log(JSON.stringify({folder,reports},null,2));
 }finally{await browser?.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
