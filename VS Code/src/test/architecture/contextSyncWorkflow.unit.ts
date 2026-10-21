import * as assert from 'node:assert/strict';
import { test } from 'node:test';
import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { ProjectAnalysisWorkflow } from '../../architecture/analysisWorkflow';
import { readProjectContext } from '../../architecture/analyzerRunner';
import { BackendApiError, ContextSyncBackend } from '../../architecture/backendClient';
import { ProjectContextSyncWorkflow } from '../../architecture/contextSyncWorkflow';
import { ProjectContext, ProjectContextSyncResponse } from '../../architecture/contracts';

const context: ProjectContext = {
  schema_version: '1.0', project_name: 'payments', project_root: '.', components: [{ name: 'demo.PaymentService' }], relationships: [],
};
const response: ProjectContextSyncResponse = {
  updated: true, project_name: 'payments', components: 1, relationships: 0, rag_invalidated: true,
};
function setup(read: (root: string) => Promise<ProjectContext> = async () => context) {
  const summary = { projectRoot: path.resolve('sample project'), contextPath: '/project/.architecture/project_context.json',
    projectName: 'payments', componentCount: 1, relationshipCount: 0 };
  const analysis = new ProjectAnalysisWorkflow({ analyze: async () => summary }, {
    folders: () => [{ name: 'payments', fsPath: summary.projectRoot, scheme: 'file' }],
    choose: async folders => folders[0], progress: task => task(), showError() {},
  });
  analysis.state = { status: 'succeeded', summary };
  const uploaded: ProjectContext[] = [];
  const backend: ContextSyncBackend = {
    baseUrl: 'https://gpu.example', syncProjectContext: async data => { uploaded.push(data); return response; },
  };
  const logs: string[] = [];
  const sync = new ProjectContextSyncWorkflow(analysis, backend, { appendLine: line => logs.push(line) }, read);
  return { sync, analysis, backend, uploaded, logs, summary };
}

test('sync reads the analyzed workspace and retains both the response and analysis result', async () => {
  let root: string | undefined;
  const { sync, analysis, summary, uploaded } = setup(async folder => { root = folder; return context; });
  const states: string[] = [];
  sync.subscribe(state => states.push(state.status));
  assert.ok(sync.canSync);
  await sync.run();
  assert.equal(root, summary.projectRoot);
  assert.deepEqual(uploaded, [context]);
  assert.deepEqual(sync.state, { status: 'synchronized', response });
  assert.deepEqual(analysis.state, { status: 'succeeded', summary });
  assert.equal(states[0], 'syncing');
  assert.ok(sync.canSync && !sync.isRunning);
});

test('backend rejection keeps the successful scan summary and allows retry', async () => {
  const { sync, analysis, backend, summary, logs } = setup();
  backend.syncProjectContext = async () => { throw new BackendApiError('http', 'Backend rejected context (HTTP 422).', 422); };
  await sync.run();
  assert.deepEqual(sync.state, { status: 'failed', message: 'Backend rejected context (HTTP 422).' });
  assert.deepEqual(analysis.state, { status: 'succeeded', summary });
  assert.ok(sync.canSync && logs.some(line => line.includes('422')));
  backend.syncProjectContext = async () => response;
  await sync.run();
  assert.equal(sync.state.status, 'synchronized');
});

test('sync requires a successful scan and never reruns the analyzer itself', async () => {
  const { sync, analysis, uploaded } = setup();
  analysis.state = { status: 'idle' };
  await sync.run();
  assert.equal(sync.state.status, 'failed');
  assert.equal(uploaded.length, 0);
});

test('concurrent sync calls share one upload', async () => {
  const { sync, backend } = setup();
  let count = 0;
  let finish: (value: ProjectContextSyncResponse) => void = () => {};
  backend.syncProjectContext = async () => { count++; return new Promise(resolve => { finish = resolve; }); };
  const first = sync.run();
  assert.equal(sync.run(), first);
  await new Promise<void>(resolve => setImmediate(resolve));
  assert.equal(count, 1);
  assert.ok(sync.isRunning && !sync.canSync);
  finish(response);
  await first;
  assert.ok(!sync.isRunning && sync.canSync);
});

test('a new scan invalidates a previous synchronization status', async () => {
  const { sync, analysis } = setup();
  await sync.run();
  await analysis.run();
  assert.equal(sync.state.status, 'not-synchronized');
  assert.ok(sync.canSync);
});

test('a backend URL change while uploading cannot mark the new backend synchronized', async () => {
  const { sync, backend } = setup();
  let configured = backend.baseUrl;
  Object.defineProperty(backend, 'baseUrl', { get: () => configured });
  backend.syncProjectContext = async () => { configured = 'https://other.example'; return response; };
  await sync.run();
  assert.equal(sync.state.status, 'not-synchronized');
});

test('a new scan during an upload cannot mark the new scan synchronized', async () => {
  const { sync, backend, analysis } = setup();
  backend.syncProjectContext = async () => { await analysis.run(); return response; };
  await sync.run();
  assert.equal(sync.state.status, 'not-synchronized');
});

test('mismatched backend summary is reported as a failed sync', async () => {
  const { sync, backend } = setup();
  backend.syncProjectContext = async () => ({ ...response, components: 500 });
  await sync.run();
  assert.equal(sync.state.status, 'failed');
});

for (const [label, contents] of [['missing', undefined], ['malformed', '{'], ['invalid', '{"components":[]}']] as const) {
  test(`${label} context file stops synchronization before any HTTP call`, async () => {
    const root = await fs.mkdtemp(path.join(os.tmpdir(), 'architecture-context-sync-'));
    try {
      if (contents !== undefined) {
        await fs.mkdir(path.join(root, '.architecture'));
        await fs.writeFile(path.join(root, '.architecture', 'project_context.json'), contents);
      }
      const { sync, uploaded, analysis } = setup(() => readProjectContext(root));
      await sync.run();
      assert.equal(sync.state.status, 'failed');
      assert.equal(uploaded.length, 0);
      assert.equal(analysis.state.status, 'succeeded');
      if (sync.state.status === 'failed') {
        assert.match(sync.state.message, label === 'missing' ? /missing/ : label === 'malformed' ? /not valid JSON/ : /missing project/);
      }
    } finally { await fs.rm(root, { recursive: true, force: true }); }
  });
}

test('reading context preserves every component and relationship field', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'architecture-context-read-'));
  try {
    await fs.mkdir(path.join(root, '.architecture'));
    const data = { ...context, components: [{ name: 'demo.PaymentService', entity_type: 'CLASS', spring_type: 'SERVICE',
      package: 'demo', file_path: 'src/main/java/demo/PaymentService.java', annotations: ['Service'],
      source_location: { start_line: 3, end_line: 8 } }],
      relationships: [{ source: 'demo.PaymentService', target: 'demo.Gateway', relationship: 'DEPENDS_ON' }] };
    await fs.writeFile(path.join(root, '.architecture', 'project_context.json'), JSON.stringify(data));
    assert.deepEqual(await readProjectContext(root), data);
  } finally { await fs.rm(root, { recursive: true, force: true }); }
});
