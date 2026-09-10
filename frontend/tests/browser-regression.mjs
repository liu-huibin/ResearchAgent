// Run against an isolated Vite server. Every /api request is intercepted;
// these tests never contact the real backend, model, or user documents.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fixtures = await mkdtemp(path.join(tmpdir(), 'researchmate-citation-test-'));
execFileSync(process.env.TEST_PYTHON || 'python', ['-B', '-c',
  'import sys; sys.path.insert(0,"tests"); from test_citations import make_browser_fixtures; make_browser_fixtures(sys.argv[1])', fixtures],
  { cwd: path.resolve('../backend') });
const browser = await chromium.launch({ channel: process.env.TEST_BROWSER_CHANNEL || 'msedge', headless: true });
const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:4173';
let tests = 0;
const errors = [];
const session = (id, title = `Session ${id}`) => ({ id, title, active_document_id: null, updated_at: new Date().toISOString() });
const processEvents = [
  { kind: 'stage', agent: 'ReaderAgent', stage: 'reader', detail: '当前依据：会话中没有可供分析的论文正文。分析取舍：将知识库检索作为证据入口。', report: '结论：已识别主要方法。\n依据：论文方法章节。\n下一步：交由 Supervisor 汇总。', status: 'succeeded' },
  { kind: 'tool', agent: 'ReaderAgent', tool: 'hybrid_retrieve', status: 'succeeded' },
  { kind: 'stage', agent: 'Supervisor', stage: 'finalize', detail: '汇总依据：以 ReaderAgent 的证据分析作为主要材料。', status: 'succeeded' },
];
const msg = (id, content, role = 'assistant', toolCalls = null) => ({ id, session_id: 1, role, content, tool_calls: toolCalls, created_at: new Date().toISOString() });
const citation = (doc, chunk) => ({ document_id: doc, chunk_index: chunk, filename: doc === 7 ? 'source.docx' : 'source.pdf',
  file_type: doc === 7 ? 'docx' : 'pdf', status: 'exact', text: doc === 7 ? 'target paragraph' : 'alpha second page',
  fragments: doc === 7
    ? [{ unit: 36 + chunk, unit_text: chunk ? 'second target' : 'target paragraph', start: 0, end: chunk ? 12 : 15, text: '', occurrence: 0 }]
    : [{ unit: 1, unit_text: 'first page alpha', start: 9, end: 14, text: 'alpha', occurrence: 0 },
       { unit: 2, unit_text: 'second page beta', start: 0, end: 10, text: 'secondpage', occurrence: 0 }] });

async function setup(mode = 'citations') {
  const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
  page.on('pageerror', error => errors.push(error.message));
  let posts = 0;
  let finished = false;
  const history = [msg(1, 'Word [citation:doc_7:chunk_0] Next [citation:doc_7:chunk_1] PDF [citation:doc_8:chunk_0]')];
  await page.route('**/api/**', async route => {
    const request = route.request();
    const url = new URL(request.url()).pathname;
    const json = data => route.fulfill({ json: data });
    if (/\/documents\/\d+\/file$/.test(url)) {
      const pdf = url.includes('/8/');
      return route.fulfill({ body: await readFile(path.join(fixtures, pdf ? 'source.pdf' : 'source.docx')),
        contentType: pdf ? 'application/pdf' : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' });
    }
    const match = url.match(/\/documents\/(\d+)\/citations\/(\d+)/);
    if (match) {
      await new Promise(resolve => setTimeout(resolve, 120));
      return json(citation(+match[1], +match[2]));
    }
    if (url === '/api/sessions') {
      if (request.method() === 'POST') return json(session(3, '新会话'));
      return json(finished
        ? [session(3, '论文方法总结'), session(1), session(2)]
        : [session(1), session(2)]);
    }
    if (url.endsWith('/document')) return json(null);
    if (url.endsWith('/list')) return json([]);
    if (url.endsWith('/metrics')) {
      const runs = finished ? [{ trace_id: 'trace-test', assistant_message_id: 3, status: 'completed', total_tokens: 5 }] : [];
      return json({ runs, latest_run: runs[0] ?? null, total_tokens: 5 });
    }
    if (url.endsWith('/messages') && request.method() === 'GET') {
      if (url.includes('/2/')) return json([msg(9, 'second-session-only')]);
      return json(mode === 'citations' ? history : finished ? [msg(2, 'question', 'user'), msg(3, 'saved-answer', 'assistant', processEvents)] : []);
    }
    if (url.endsWith('/messages') && request.method() === 'POST') {
      posts++;
      if (mode === 'delayed') {
        await new Promise(resolve => setTimeout(resolve, 1000));
        try { return await route.fulfill({ contentType: 'text/event-stream', body: 'event: token\ndata: {"content":"stale-answer"}\n\n' }); }
        catch { return; }
      }
      if (mode === 'success') finished = true;
      const body = 'event: start\r\ndata: {"trace_id":"trace-test"}\r\n\r\n: keepalive\r\n\r\nevent: agent\r\ndata: {"agent":"ReaderAgent","stage":"reader","detail":"当前依据：会话中没有可供分析的论文正文。分析取舍：将知识库检索作为证据入口。"}\r\n\r\nevent: action\r\ndata: {"agent":"ReaderAgent","tool":"hybrid_retrieve"}\r\n\r\nevent: observation\r\ndata: {"agent":"ReaderAgent","tool":"hybrid_retrieve","is_error":false}\r\n\r\nevent: report\r\ndata: {"agent":"ReaderAgent","stage":"reader","content":"结论：已识别主要方法。依据：论文方法章节。下一步：交由 Supervisor 汇总。"}\r\n\r\nevent: token\r\ndata: {"content":"visible-partial"}\r\n\r\nevent: metrics\r\ndata: {"status":"completed","total_tokens":5}\r\n\r\n'
        + (finished ? 'event: done\r\ndata: {"trace_id":"trace-test","message_id":3,"status":"completed","persisted":true}\r\n\r\n' : '');
      return route.fulfill({ contentType: 'text/event-stream', body });
    }
    throw new Error(`Unmocked API ${request.method()} ${url}`);
  });
  await page.goto(base);
  await page.getByText('Session 1', { exact: true }).waitFor();
  await page.locator('textarea').waitFor();
  return { page, posts: () => posts };
}

try {
  {
    const { page } = await setup();
    const firstSource = page.getByTitle('定位来源文档 7 · 分块 1');
    await firstSource.click();
    await page.getByText('定位中…', { exact: true }).waitFor();
    await page.locator('mark[data-citation]').first().waitFor();
    assert.equal(await page.locator('mark[data-citation]').allTextContents().then(v => v.join('').replace(/\s/g, '')), 'targetparagraph');
    assert.ok(await page.locator('mark[data-citation]').first().evaluate(el => el.getBoundingClientRect().top < innerHeight));
    await page.getByTitle('定位来源文档 7 · 分块 2').click();
    await page.waitForFunction(() => [...document.querySelectorAll('mark[data-citation]')].map(m => m.textContent).join('') === 'second target');
    await page.getByTitle('定位来源文档 7 · 分块 1').click();
    await page.waitForFunction(() => [...document.querySelectorAll('mark[data-citation]')].map(m => m.textContent).join('').replace(/\s/g, '') === 'targetparagraph');
    await page.getByTitle('定位来源文档 8 · 分块 1').click();
    await page.locator('[data-page="2"] mark[data-citation]').waitFor();
    assert.equal(await page.locator('[data-page="1"] mark[data-citation]').allTextContents().then(v => v.join('')), 'alpha');
    assert.equal(await page.locator('[data-page="2"] mark[data-citation]').allTextContents().then(v => v.join('')), 'second page');
    await page.getByRole('button', { name: '+', exact: true }).click();
    await page.waitForTimeout(800); // react-pdf recreates the text layer after zoom
    await page.locator('[data-page="2"] mark[data-citation]').waitFor();
    tests += 4;
    await page.close();
  }
  {
    const { page, posts } = await setup('success');
    await page.locator('textarea').fill('question');
    await page.getByRole('button', { name: '发送', exact: true }).click();
    await page.getByText('saved-answer', { exact: true }).waitFor();
    await page.getByText('推理与协作说明', { exact: true }).waitFor();
    const persistedReport = page.getByText('Agent 公开报告', { exact: true }).locator('..');
    assert.match(await persistedReport.innerText(), /结论：已识别主要方法/);
    assert.equal(await page.locator('div.font-medium').filter({ hasText: '论文阅读 · 阅读材料并提取相关证据' }).count(), 1);
    assert.equal(await page.locator('div.font-medium').filter({ hasText: '论文阅读 · hybrid_retrieve' }).count(), 1);
    assert.equal(await page.getByText('当前依据：会话中没有可供分析的论文正文。分析取舍：将知识库检索作为证据入口。', { exact: true }).count(), 1);
    assert.equal(posts(), 1);
    assert.equal(await page.getByText('visible-partial', { exact: true }).count(), 0);
    tests++;
    await page.close();
  }
  {
    const { page, posts } = await setup('success');
    await page.getByRole('button', { name: '+ 新建会话', exact: true }).click();
    await page.locator('textarea').fill('first question');
    await page.getByRole('button', { name: '发送', exact: true }).click();
    await page.getByText('saved-answer', { exact: true }).waitFor();
    await page.getByText('论文方法总结', { exact: true }).waitFor();
    assert.equal(await page.getByText('新会话', { exact: true }).count(), 0);
    assert.equal(posts(), 1);
    tests++;
    await page.close();
  }
  {
    const { page, posts } = await setup('disconnect');
    await page.locator('textarea').fill('question');
    await page.getByRole('button', { name: '发送', exact: true }).click();
    await page.getByText('尚未确认保存。', { exact: false }).waitFor({ timeout: 20000 });
    await page.getByText('当前依据：会话中没有可供分析的论文正文。', { exact: false }).waitFor();
    const liveReport = page.getByText('Agent 公开报告', { exact: true }).locator('..');
    assert.match(await liveReport.innerText(), /结论：已识别主要方法/);
    assert.equal(await page.getByText('visible-partial', { exact: true }).count(), 1);
    assert.equal(posts(), 1);
    tests++;
    await page.close();
  }
  {
    const { page } = await setup('delayed');
    await page.locator('textarea').fill('question');
    await page.getByRole('button', { name: '发送', exact: true }).click();
    await page.getByText('Session 2', { exact: true }).click();
    await page.getByText('second-session-only', { exact: true }).waitFor();
    await page.waitForTimeout(1200);
    assert.equal(await page.getByText('stale-answer', { exact: true }).count(), 0);
    tests++;
    await page.close();
  }
  assert.deepEqual(errors, []);
  console.log(`Browser regression passed: ${tests} checks (real PDF/DOCX rendering; isolated API fixtures).`);
} finally {
  await browser.close();
  await rm(fixtures, { recursive: true, force: true }); // only mkdtemp-owned fixtures
}
