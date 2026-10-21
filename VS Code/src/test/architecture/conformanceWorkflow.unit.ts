import * as assert from 'node:assert/strict';
import { test, TestContext } from 'node:test';
import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { ProjectAnalysisWorkflow } from '../../architecture/analysisWorkflow';
import { BackendApiError, ConformanceBackend } from '../../architecture/backendClient';
import { ConformanceWorkflow } from '../../architecture/conformanceWorkflow';
import { ProjectContextSyncWorkflow } from '../../architecture/contextSyncWorkflow';
import { ConformanceDiagnostic, ConformanceDiagnostics, ConformanceSourceMapper } from '../../architecture/conformanceSources';
import { ConformanceResponse } from '../../architecture/contracts';
import { conformanceResponse, exampleViolation } from './conformanceFixtures';

async function setup(t: TestContext) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'architecture-conformance-'));
  await fs.mkdir(path.join(root, 'src'));
  await fs.writeFile(path.join(root, 'src', 'Example.java'), 'class Example {}');
  let analyzerCalls = 0;
  const summary = { projectRoot: root, projectName: 'payments', contextPath: path.join(root, '.architecture/project_context.json'),
    componentCount: 1, relationshipCount: 0 };
  const analysis = new ProjectAnalysisWorkflow({ analyze: async () => { analyzerCalls++; return summary; } }, {
    folders: () => [{ name: 'payments', fsPath: root, scheme: 'file' }], choose: async folders => folders[0],
    progress: task => task(), showError() {},
  });
  const logs: string[] = [];
  const logger = { appendLine: (line: string) => logs.push(line) };
  const sync = new ProjectContextSyncWorkflow(analysis, {
    baseUrl: 'https://backend.example', syncProjectContext: async () => ({ updated: true, project_name: 'payments',
      components: 1, relationships: 0, rag_invalidated: true }),
  }, logger, async () => ({ schema_version: '1.0', project_name: 'payments', project_root: '.', components: [{}], relationships: [] }));
  await analysis.run();
  await sync.run();
  let response = conformanceResponse();
  let calls = 0;
  const backend: ConformanceBackend = {
    baseUrl: 'https://backend.example', checkConformance: async () => { calls++; return response; },
  };
  const sink = { entries: [] as ConformanceDiagnostic[], clears: 0, opens: [] as string[] };
  const mapper = new ConformanceSourceMapper(logger);
  const diagnostics: ConformanceDiagnostics = {
    clear: () => { sink.entries = []; sink.clears++; }, prepare: (project, violations) => mapper.prepare(project, violations),
    replace: entries => { sink.entries = [...entries]; },
    open: async (project, violation) => { sink.opens.push(violation.violation_id); return !!await mapper.locate(project, violation); },
  };
  const host = { progress: async (task: () => Promise<void>, _cancel: () => void) => task() };
  const workflow = new ConformanceWorkflow(analysis, sync, backend, diagnostics, logger, host);
  t.after(async () => {
    workflow.dispose(); sync.dispose(); analysis.dispose();
    assert.equal(path.dirname(root), path.resolve(os.tmpdir()));
    await fs.rm(root, { recursive: true, force: true });
  });
  return { workflow, analysis, sync, backend, diagnostics, sink, logs, host, root,
    calls: () => calls, analyzerCalls: () => analyzerCalls, setResponse: (value: ConformanceResponse) => { response = value; } };
}

test('check returns backend violations, publishes diagnostics and never reruns Java or sync', async t => {
  const { workflow, sink, calls, analyzerCalls, logs } = await setup(t);
  assert.ok(workflow.canCheck);
  await workflow.run();
  assert.equal(workflow.state.status, 'checked');
  assert.equal(sink.entries.length, 1);
  assert.equal(sink.entries[0].range.startLine, 0);
  assert.equal(calls(), 1);
  assert.equal(analyzerCalls(), 1);
  assert.ok(logs.some(line => line.includes('1 diagnostics created')));
  if (workflow.state.status === 'checked') { assert.deepEqual(workflow.state.result, conformanceResponse()); }
});
test('conformant and repeated results replace and clear old diagnostics', async t => {
  const { workflow, sink, setResponse } = await setup(t);
  await workflow.run();
  await workflow.run();
  assert.equal(sink.entries.length, 1);
  setResponse(conformanceResponse([]));
  await workflow.run();
  assert.deepEqual(sink.entries, []);
  assert.equal(workflow.state.status, 'checked');
  if (workflow.state.status === 'checked') { assert.ok(workflow.state.result.conformant); }
});
test('preconditions reject unsynchronized or unanalyzed projects without HTTP', async t => {
  const { workflow, analysis, sync, calls } = await setup(t);
  sync.reset();
  await workflow.run();
  assert.equal(calls(), 0);
  assert.equal(workflow.state.status, 'failed');
  if (workflow.state.status === 'failed') { assert.match(workflow.state.message, /Sync Project Context/); }
  analysis.state = { status: 'idle' };
  await workflow.run();
  assert.equal(calls(), 0);
  if (workflow.state.status === 'failed') { assert.match(workflow.state.message, /Analyze a project/); }
});
test('a new analysis clears diagnostics and requires synchronization again', async t => {
  const { workflow, analysis, sink } = await setup(t);
  await workflow.run();
  await analysis.run();
  assert.equal(workflow.state.status, 'stale');
  assert.deepEqual(sink.entries, []);
  assert.equal(workflow.canCheck, false);
});
test('re-sync and rule approval invalidate previous conformance', async t => {
  const { workflow, sync, sink } = await setup(t);
  await workflow.run();
  await sync.run();
  assert.equal(workflow.state.status, 'stale');
  assert.deepEqual(sink.entries, []);
  assert.ok(workflow.canCheck);
  await workflow.run();
  workflow.invalidate();
  assert.equal(workflow.state.status, 'stale');
  assert.deepEqual(sink.entries, []);
});

test('re-sync publishes enabled eligibility after its active promise clears, without another invalidation', async t => {
  const { workflow, analysis, sync, calls } = await setup(t);
  await workflow.run();
  await analysis.run();
  assert.equal(workflow.canCheck, false);
  const notifications: { enabled: boolean; syncing: boolean; state: unknown }[] = [];
  workflow.subscribe(state => notifications.push({ enabled: workflow.canCheck, syncing: sync.isRunning, state }));
  await sync.run();
  assert.equal(workflow.state.status, 'stale');
  assert.ok(notifications.some(item => item.syncing && !item.enabled));
  assert.equal(notifications.at(-1)?.enabled, true);
  assert.equal(notifications.at(-1)?.syncing, false);
  assert.equal(notifications.at(-1)?.state, notifications.at(-2)?.state);
  await workflow.run();
  assert.equal(calls(), 2);
});
for (const [label, change] of [
  ['missing location', { start_line: undefined, end_line: undefined }], ['invalid location', { start_line: -1 }],
  ['missing file', { file_path: 'gone.java' }], ['traversal', { file_path: '../../outside.java' }],
] as const) {
  test(`${label} stays in results but produces no diagnostic`, async t => {
    const { workflow, setResponse, sink } = await setup(t);
    setResponse(conformanceResponse([{ ...exampleViolation, ...change }]));
    await workflow.run();
    assert.equal(workflow.state.status, 'checked');
    assert.deepEqual(sink.entries, []);
    if (workflow.state.status === 'checked') {
      assert.equal(workflow.state.result.violations.length, 1);
      assert.deepEqual(workflow.state.navigableViolationIds, []);
    }
  });
}
test('backend failure clears old diagnostics and gives independent error state', async t => {
  const { workflow, backend, sink } = await setup(t);
  await workflow.run();
  backend.checkConformance = async () => { throw new BackendApiError('http', 'Backend failed (HTTP 503).', 503); };
  await workflow.run();
  assert.deepEqual(workflow.state, { status: 'failed', message: 'Backend failed (HTTP 503).' });
  assert.deepEqual(sink.entries, []);
});
test('concurrent panel and palette calls share one request', async t => {
  const { workflow, backend } = await setup(t);
  let finish: (result: ConformanceResponse) => void = () => {};
  backend.checkConformance = async () => new Promise(resolve => { finish = resolve; });
  const first = workflow.run();
  assert.equal(workflow.run(), first);
  assert.ok(workflow.isRunning);
  finish(conformanceResponse());
  await first;
  assert.equal(workflow.state.status, 'checked');
});
test('cancellation before HTTP does not publish a result', async t => {
  const { workflow, host, calls } = await setup(t);
  host.progress = async (task, cancel) => { cancel(); await task(); };
  await workflow.run();
  assert.equal(calls(), 0);
  assert.equal(workflow.state.status, 'cancelled');
});
test('late response after cancellation cannot restore diagnostics', async t => {
  const { workflow, backend, sink } = await setup(t);
  let finish: (result: ConformanceResponse) => void = () => {};
  let signal: AbortSignal | undefined;
  backend.checkConformance = async cancellation => { signal = cancellation; return new Promise(resolve => { finish = resolve; }); };
  const pending = workflow.run();
  workflow.cancel();
  assert.ok(signal?.aborted);
  finish(conformanceResponse());
  await pending;
  assert.equal(workflow.state.status, 'cancelled');
  assert.deepEqual(sink.entries, []);
});
test('results prepared before a re-analysis cannot publish after it', async t => {
  const { workflow, diagnostics, analysis, sink } = await setup(t);
  let finish: (entries: ConformanceDiagnostic[]) => void = () => {};
  diagnostics.prepare = async () => new Promise(resolve => { finish = resolve; });
  const pending = workflow.run();
  await new Promise<void>(resolve => setImmediate(resolve));
  await analysis.run();
  finish([]);
  await pending;
  assert.equal(workflow.state.status, 'stale');
  assert.deepEqual(sink.entries, []);
});
test('backend URL changes invalidate the acknowledgement and late conformance results', async t => {
  const { workflow, backend, sink } = await setup(t);
  let url = backend.baseUrl;
  Object.defineProperty(backend, 'baseUrl', { get: () => url });
  backend.checkConformance = async () => { url = 'https://other.example'; return conformanceResponse(); };
  await workflow.run();
  assert.equal(workflow.state.status, 'stale');
  assert.equal(workflow.canCheck, false);
  assert.deepEqual(sink.entries, []);
});
test('a different backend active project is never applied to the selected workspace', async t => {
  const { workflow, setResponse, sink, sync } = await setup(t);
  setResponse({ ...conformanceResponse(), project_name: 'unrelated-project' });
  await workflow.run();
  assert.equal(workflow.state.status, 'failed');
  assert.equal(sync.state.status, 'not-synchronized');
  assert.deepEqual(sink.entries, []);
});
test('navigation resolves only IDs from the current checked result', async t => {
  const { workflow, sink } = await setup(t);
  await workflow.run();
  assert.equal(await workflow.navigate('not-a-violation'), false);
  assert.equal(await workflow.navigate(exampleViolation.violation_id), true);
  assert.deepEqual(sink.opens, [exampleViolation.violation_id]);
  workflow.clear();
  assert.equal(workflow.state.status, 'not-checked');
  assert.equal(await workflow.navigate(exampleViolation.violation_id), false);
});
