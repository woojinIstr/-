import {test} from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {spawn} from 'node:child_process';
import {existsSync} from 'node:fs';
import {mkdtemp, rm, unlink} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {JSDOM} from 'jsdom';

test('first visit can add stock and plan a starter menu with the same shortage as shopping', async () => {
  const tmp = await mkdtemp(join(tmpdir(), 'nextmeal-start-'));
  const python = process.env.CODEX_PRIMARY_RUNTIME_PYTHON || 'python3';
  const server = spawn(python, ['-m', 'uvicorn', 'app.main:create_app', '--factory',
    '--host', '127.0.0.1', '--port', '0'], {
    cwd: existsSync('../backend/app/main.py') ? '../backend' : '..',
    env: {...process.env, APP_ENV: 'development', APP_MODE: 'local', SQLITE_PATH: join(tmp, 'test.db'),
      OPENROUTER_API_KEY: '', OPENAI_API_KEY: ''},
    stdio: 'pipe',
  });
  const output = new URL('./.quick-start-generated.mjs', import.meta.url);
  const realFetch = global.fetch;
  const dom = new JSDOM('<!doctype html><div></div>', {url: 'http://localhost:8000/', pretendToBeVisual: true});
  global.window = dom.window;
  global.document = dom.window.document;
  global.HTMLElement = dom.window.HTMLElement;
  global.IS_REACT_ACT_ENVIRONMENT = true;
  window.scrollTo = () => {};
  const React = await import('react');
  const {render, screen, fireEvent, within, cleanup} = await import('@testing-library/react');
  try {
    const base = await new Promise((resolve, reject) => {
      server.stderr.on('data', data => {
        const match = data.toString().match(/Uvicorn running on (http:\/\/127\.0\.0\.1:\d+)/);
        if (match) resolve(match[1]);
      });
      server.once('exit', code => reject(new Error('Server exited ' + code)));
      setTimeout(() => reject(new Error('Server startup timeout')), 15000).unref();
    });
    await build({entryPoints: ['src/IntegratedApp.jsx'], outfile: output.pathname, bundle: true,
      platform: 'node', format: 'esm', external: ['react', 'lucide-react'], define: {'import.meta.env': '{}'}});
    const App = (await import(output.href)).default;
    global.fetch = (url, options) => url === '/app-config'
      ? Promise.resolve({ok: true, json: async () => ({mode: 'local', url: '', key: '', api: base})})
      : realFetch(url, options);
    const load = async () => (await realFetch(base + '/v3/workspace')).json();
    const click = async (name, scope = screen) => fireEvent.click(await scope.findByRole('button', {name, exact: true}));
    const fill = (name, value) => fireEvent.change(screen.getByLabelText(name, {exact: true}), {target: {value}});
    const porkCard = async () => within((await screen.findByRole('heading',
      {name: '삼겹살구이', exact: true})).closest('section'));
    const review = async () => within(await screen.findByRole('dialog', {name: '식사 계획 확인'}));
    render(React.createElement(App));

    await click('재료 추가하고 메뉴 찾기');
    assert.deepEqual((await load()).workspace.ingredients, []);
    fill('재료 한 줄 입력','달걀 -2개');
    await click('수량 확인하기');
    await screen.findByRole('alert');
    fill('재료 한 줄 입력','삼겹살 250g, 계란 2개, 햇반 1개');
    await click('수량 확인하기');
    assert.equal(screen.getByLabelText('단위 2').value, 'count');
    assert.equal(screen.getByLabelText('포장 1개당 중량 3 (g)').value, '');
    fill('포장 1개당 중량 3 (g)','210');
    await click('저장하고 메뉴 찾기');
    assert.ok((await porkCard()).getByText('이 끼니는 지금 있는 재료로 만들 수 있어요'));
    const stocked = await load();
    assert.deepEqual(stocked.workspace.recipes, []);
    assert.deepEqual(stocked.workspace.inventory.map(item => item.quantity), [250, 2, 210]);
    assert.equal(stocked.workspace.products[0].pack_size,210);
    assert.equal(stocked.revision, 1);

    fireEvent.click(screen.getByText(/^상세 조건 ·/));
    fill('식사 시간', 'lunch');
    await click('20분');
    await click('식사에 추가', await porkCard());
    assert.ok((await review()).getByText('삼겹살구이'));
    assert.equal((await load()).workspace.meals.length, 0);
    await click('이대로 적용', await review());
    await screen.findByRole('heading', {name: '식사 계획', exact: true});
    assert.deepEqual((await load()).workspace.recipes, []);

    await click('메뉴 찾기');
    await screen.findByRole('heading', {name: '삶은 달걀', exact: true});
    assert.equal(Boolean(screen.queryByRole('heading', {name: '삼겹살구이', exact: true})), false);
    fireEvent.click(screen.getByLabelText('있는 재료만'));
    assert.ok((await porkCard()).getByText('더 필요한 재료 · 삼겹살 50g'));
    await click('식사에 추가', await porkCard());
    assert.ok((await review()).getByText('50g', {exact: true}));
    await click('메뉴 다시 고르기', await review());
    assert.equal((await load()).workspace.meals.length, 1);
  } finally {
    global.fetch = realFetch;
    cleanup();
    dom.window.close();
    server.kill();
    await unlink(output).catch(() => {});
    await rm(tmp, {recursive: true, force: true});
  }
});
