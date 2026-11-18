const status = document.querySelector('#status');
const pages = document.querySelector('#pages');
const pageInput = document.querySelector('#page');
const zoom = document.querySelector('#zoom');
let engine, doc, version, count = 0, password, polling = false;

function message(text, error = false) {
  status.textContent = text;
  status.classList.toggle('error', error);
}

function paint(rhwpDocument, page) {
  const canvas = document.createElement('canvas');
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', `문서 ${page} 페이지`);
  rhwpDocument.renderPageToCanvas(page - 1, canvas, Number(zoom.value));
  return canvas;
}

function navigate(delta = 0) {
  if (!doc) return;
  const page = Math.max(1, Math.min(count, (Number(pageInput.value) || 1) + delta));
  try {
    const canvas = paint(doc, page);
    pages.replaceChildren(canvas);
    pageInput.value = page;
  } catch (error) { message(String(error), true); }
}

async function poll() {
  if (!engine || polling) return;
  polling = true;
  let candidate;
  try {
    const response = await fetch('api/state', {cache: 'no-store'});
    if (!response.ok) throw Error(`파일 상태 조회 실패 (${response.status})`);
    const state = await response.json();
    if (state.error) throw Error(`최신 파일을 읽지 못했습니다. 이전 화면 유지: ${state.error}`);
    if (state.version === version) {
      if (status.classList.contains('error')) message(`정상 파일 확인 · ${version.slice(0,12)} · rhwp 조판`);
      return;
    }
    const file = await fetch(`api/document/${state.version}`, {cache: 'no-store'});
    if (file.status === 409) return;
    if (!file.ok) throw Error(`파일 로드 실패 (${file.status})`);
    const bytes = new Uint8Array(await file.arrayBuffer());
    candidate = state.encrypted ? engine.HwpDocument.openWithPassword(bytes, password) : new engine.HwpDocument(bytes);
    const nextCount = candidate.pageCount();
    if (!nextCount) throw Error('rhwp가 표시할 페이지를 생성하지 못했습니다.');
    const page = Math.max(1, Math.min(nextCount, Number(pageInput.value) || 1));
    const canvas = paint(candidate, page);
    // Check the source once more before committing an asynchronous candidate.
    const latest = await (await fetch('api/state', {cache: 'no-store'})).json();
    if (latest.version !== state.version || latest.error) return;
    const previous = doc;
    doc = candidate; candidate = undefined;
    count = nextCount; version = state.version;
    pageInput.max = count; pageInput.value = page;
    document.querySelector('#count').textContent = `/ ${count}`;
    pages.replaceChildren(canvas);
    previous?.free();
    message(`반영 ${new Date().toLocaleTimeString()} · ${version.slice(0, 12)} · rhwp 조판`);
    window.hwpxViewerState = {version, count, page};
  } catch (error) { message(String(error), true); }
  finally { candidate?.free(); polling = false; }
}

document.querySelector('#previous').addEventListener('click', () => navigate(-1));
document.querySelector('#next').addEventListener('click', () => navigate(1));
pageInput.addEventListener('change', () => navigate());
zoom.addEventListener('change', () => navigate());
addEventListener('beforeunload', () => { doc?.free(); password = undefined; });
try {
  engine = await import('./rhwp/rhwp.js');
  await engine.default({module_or_path: new URL('./rhwp/rhwp_bg.wasm', import.meta.url)});
  const credentials = await fetch('api/credentials', {method: 'POST', body: '', cache: 'no-store'});
  if (!credentials.ok) throw Error('뷰어 인증 세션을 열지 못했습니다.');
  password = (await credentials.json()).password;
  await Promise.all([
    new FontFace('Noto Sans KR', 'url(fonts/NotoSansKR-Regular.woff2)').load(),
    new FontFace('Noto Sans KR', 'url(fonts/NotoSansKR-Bold.woff2)', {weight:'700'}).load(),
    new FontFace('Noto Serif KR', 'url(fonts/NotoSerifKR-Regular.woff2)').load(),
  ].map(async face => document.fonts.add(await face)));
  await document.fonts.ready;
  await poll();
  setInterval(poll, 500);
} catch (error) { message(`rhwp 초기화 실패: ${error}`, true); }
