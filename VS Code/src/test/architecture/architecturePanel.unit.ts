import * as assert from 'node:assert/strict';
import { test, TestContext } from 'node:test';
import * as fs from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { createRequire } from 'node:module';
import { runInNewContext } from 'node:vm';
import type * as vscode from 'vscode';
import type { ProjectAnalysisWorkflow } from '../../architecture/analysisWorkflow';
import type { ProjectContextSyncWorkflow } from '../../architecture/contextSyncWorkflow';
import type { ConformanceState, ConformanceWorkflow } from '../../architecture/conformanceWorkflow';
import { ActiveEditorDocument, ViolationGroups } from '../../architecture/violationGrouping';
import { conformanceResponse, exampleViolation } from './conformanceFixtures';

interface ViewMessage { type: string; state: ConformanceState; activeFile?: { filePath: string }; violationGroups?: ViolationGroups; }
async function panel(t: TestContext, initialMode = 'product') {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'architecture-panel-editor-'));
  await fs.mkdir(path.join(root, 'src'));
  for (const name of ['Example.java', 'Other.java', 'Clean.java']) { await fs.writeFile(path.join(root, 'src', name), 'class Example {}'); }
  const editor = (file: string, languageId = 'java') => ({ document: { uri: { scheme: 'file', fsPath: file }, languageId, isUntitled: false } });
  const editorEvents = new Set<() => void>();
  const configurationEvents = new Set<(event: { affectsConfiguration: (section: string) => boolean }) => void>();
  let backendUrl = 'http://127.0.0.1:8000';
  let uiMode = initialMode;
  const allMessages: Record<string, unknown>[] = [];
  const messageWaiters = new Map<string, (message: unknown) => void>();
  const remembered = new Map<string, unknown>();
  let invalidations = 0, nativeConfirmations = 0;
  const backendMessages: { configured: boolean; host?: string }[] = [];
  const conformanceEvents = new Set<() => void>();
  const navigated: string[] = [];
  const second = { ...exampleViolation, violation_id: 'OTHER', file_path: 'src/Other.java' };
  const conformance = {
    state: { status: 'checked', result: conformanceResponse([exampleViolation, second]),
      navigableViolationIds: [exampleViolation.violation_id, second.violation_id] } as ConformanceState,
    canCheck: true, isRunning: false,
    subscribe: (listener: () => void) => { conformanceEvents.add(listener); return () => conformanceEvents.delete(listener); },
    run: async () => { throw new Error('An editor change must not request conformance'); },
    navigate: async (id: string) => { navigated.push(id); return true; },
    invalidate: () => { invalidations++; },
  };
  let receive: (message: unknown) => Promise<void> = async () => {};
  let onDispose = () => {};
  let disposed = false;
  const messages: ViewMessage[] = [];
  const waiting: { matches: (message: ViewMessage) => boolean; resolve: (message: ViewMessage) => void }[] = [];
  const webviewPanel = {
    reveal() {},
    onDidDispose: (callback: () => void) => { onDispose = callback; },
    dispose: () => { if (!disposed) { disposed = true; onDispose(); } },
    webview: {
      html: '', onDidReceiveMessage: (callback: typeof receive) => { receive = callback; return { dispose() {} }; },
      postMessage: async (message: ViewMessage) => {
        allMessages.push(message as unknown as Record<string, unknown>);
        messageWaiters.get(message.type)?.(message);
        messageWaiters.delete(message.type);
        if (message.type === 'backendStatus') { backendMessages.push(message as unknown as { configured: boolean; host?: string }); }
        if (message.type !== 'conformance') { return true; }
        messages.push(message);
        for (const waiter of [...waiting]) {
          if (waiter.matches(message)) { waiting.splice(waiting.indexOf(waiter), 1); waiter.resolve(message); }
        }
        return true;
      },
    },
  };
  const api = {
    ViewColumn: { Beside: 2 },
    ProgressLocation: { Notification: 15 },
    window: {
      activeTextEditor: editor(path.join(root, 'src', 'Example.java')) as { document: ActiveEditorDocument } | undefined,
      createWebviewPanel: () => webviewPanel,
      withProgress: async (_options: unknown, task: () => Promise<void>) => task(),
      showWarningMessage: async () => { nativeConfirmations++; return 'Approve anyway'; },
      onDidChangeActiveTextEditor: (callback: () => void) => { editorEvents.add(callback); return { dispose: () => editorEvents.delete(callback) }; },
    },
    workspace: {
      getConfiguration: () => ({ get: (key: string, fallback: unknown) => key === 'uiMode' ? uiMode : key === 'aiBackendUrl' ? backendUrl : fallback }),
      onDidChangeConfiguration: (callback: (event: { affectsConfiguration: (section: string) => boolean }) => void) => {
        configurationEvents.add(callback); return { dispose: () => configurationEvents.delete(callback) };
      },
    },
  };
  const modulePath = path.resolve(__dirname, '../../architecture/architecturePanel.js');
  const actualRequire = createRequire(modulePath);
  const exports = {} as typeof import('../../architecture/architecturePanel');
  runInNewContext(readFileSync(modulePath, 'utf8'), { exports, URL, require: (name: string) => name === 'vscode' ? api : actualRequire(name) });
  const context = { subscriptions: [], workspaceState: { get: (key: string) => remembered.get(key),
    update: async (key: string, value: unknown) => { remembered.set(key, value); } } } as unknown as vscode.ExtensionContext;
  const analysis = { state: { status: 'succeeded', summary: { projectRoot: root } }, subscribe: () => () => {} } as unknown as ProjectAnalysisWorkflow;
  const sync = { state: { status: 'synchronized' }, isRunning: false, canSync: true, subscribe: () => () => {} } as unknown as ProjectContextSyncWorkflow;
  exports.ArchitecturePanel.show(context, { appendLine() {} } as unknown as vscode.OutputChannel, analysis, sync,
    conformance as unknown as ConformanceWorkflow);
  t.after(async () => {
    webviewPanel.dispose();
    assert.equal(path.dirname(root), path.resolve(os.tmpdir()));
    await fs.rm(root, { recursive: true, force: true });
  });
  const next = (matches: (message: ViewMessage) => boolean = () => true) => new Promise<ViewMessage>(resolve => waiting.push({ matches, resolve }));
  const activate = (file: string | undefined, languageId = 'java') => {
    api.window.activeTextEditor = file ? editor(file, languageId) : undefined;
    for (const callback of editorEvents) { callback(); }
  };
  const configureBackend = (url: string) => {
    backendUrl = url;
    for (const callback of configurationEvents) {
      callback({ affectsConfiguration: section => section === 'architectureGovernance.aiBackendUrl' });
    }
  };
  const configureMode = (mode: string) => {
    uiMode = mode;
    for (const callback of configurationEvents) { callback({ affectsConfiguration: section => section === 'architectureGovernance.uiMode' }); }
  };
  return { root, conformance, conformanceEvents, messages, navigated, editorEvents, configurationEvents,
    backendMessages, configureBackend, configureMode, allMessages, remembered, next, activate,
    html: () => webviewPanel.webview.html, invalidations: () => invalidations, nativeConfirmations: () => nativeConfirmations,
    nextType: (type: string) => new Promise(resolve => messageWaiters.set(type, resolve)),
    receive: (message: unknown) => receive(message), dispose: () => webviewPanel.dispose() };
}

test('ready and active-editor events group cached results without running conformance', { timeout: 5000 }, async t => {
  const host = await panel(t);
  const ready = host.next();
  await host.receive({ type: 'ready' });
  assert.equal((await ready).violationGroups?.currentFileViolations[0].violation_id, exampleViolation.violation_id);
  const changed = host.next();
  host.activate(path.join(host.root, 'src', 'Other.java'));
  const message = await changed;
  assert.equal(message.violationGroups?.currentFileViolations[0].violation_id, 'OTHER');
  assert.equal(message.violationGroups?.otherViolations[0].violation_id, exampleViolation.violation_id);
  await host.receive({ type: 'openViolation', violationId: 'OTHER' });
  assert.deepEqual(host.navigated, ['OTHER']);
});
test('non-Java, outside and absent editors restore the normal project-wide view', { timeout: 5000 }, async t => {
  const host = await panel(t);
  for (const [file, language] of [[path.join(host.root, 'README.md'), 'markdown'], [path.join(path.dirname(host.root), 'Outside.java'), 'java'], [undefined, 'java']] as const) {
    const pending = host.next();
    host.activate(file, language);
    const message = await pending;
    assert.equal(message.activeFile, undefined);
    assert.equal(message.violationGroups?.otherViolations.length, 2);
  }
});
test('new results and stale states regroup or clear the current-file view', { timeout: 5000 }, async t => {
  const host = await panel(t);
  host.conformance.state = { status: 'checked', result: conformanceResponse([]), navigableViolationIds: [] };
  const refreshed = host.next();
  for (const listener of host.conformanceEvents) { listener(); }
  assert.equal((await refreshed).violationGroups?.currentFileViolations.length, 0);
  host.conformance.state = { status: 'stale', message: 'Analyze and sync again.' };
  const stale = host.next();
  for (const listener of host.conformanceEvents) { listener(); }
  const message = await stale;
  assert.equal(message.activeFile, undefined);
  assert.equal(message.violationGroups, undefined);
});
test('rapid editor changes publish the latest grouping and listeners are disposed with the panel', { timeout: 5000 }, async t => {
  const host = await panel(t);
  const pending = host.next(message => message.activeFile?.filePath === 'src/Other.java');
  host.activate(path.join(host.root, 'src', 'Example.java'));
  host.activate(path.join(host.root, 'src', 'Other.java'));
  await pending;
  assert.ok(host.messages.every(message => message.activeFile?.filePath !== 'src/Example.java'));
  assert.equal(host.editorEvents.size, 1);
  host.dispose();
  assert.equal(host.editorEvents.size, 0);
  assert.equal(host.conformanceEvents.size, 0);
  assert.equal(host.configurationEvents.size, 0);
});

test('backend configuration display publishes only the hostname and updates without a request', async t => {
  const host = await panel(t);
  await host.receive({ type: 'ready' });
  assert.equal(host.backendMessages.at(-1)?.host, '127.0.0.1');
  host.configureBackend('https://gpu.example/private/backend');
  const configured = host.backendMessages.at(-1);
  assert.equal(configured?.configured, true);
  assert.equal(configured?.host, 'gpu.example');
  assert.ok(!JSON.stringify(configured).includes('/private/backend'));
  host.configureBackend('invalid URL');
  assert.equal(host.backendMessages.at(-1)?.configured, false);
  assert.equal(host.backendMessages.at(-1)?.host, undefined);
});

test('both UI modes use one panel and switching keeps host state with a local refresh', async t => {
  const host = await panel(t);
  assert.match(host.html(), /id="developer-ui" hidden/);
  assert.match(host.html(), /id="product-ui">/);
  assert.doesNotMatch(host.html(), /cdn\.jsdelivr|<link|<script[^>]+src=/);
  const originalHtml = host.html();
  host.configureMode('developer');
  assert.equal(host.allMessages.at(-1)?.mode, 'developer');
  host.configureMode('product');
  assert.equal(host.allMessages.at(-1)?.mode, 'product');
  assert.equal(host.html(), originalHtml);
  assert.equal(host.conformance.state.status, 'checked');
});

test('developer setting initially renders the preserved technical UI', async t => {
  const host = await panel(t, 'developer');
  assert.match(host.html(), /id="product-ui" hidden/);
  assert.match(host.html(), /id="developer-ui">/);
  assert.match(host.html(), /id="raw-output" hidden/);
  assert.match(host.html(), /Generated output/);
});

const generated = { generated_text: 'unchanged model output', json_valid: true, schema_valid: true, validation_errors: [], retrieved_context: [],
  rule: { status: 'VALID', reason_code: null, rule: { rule_type: 'COMPONENT_ACCESS',
    source: { entity_type: 'COMPONENT', name: 'PaymentService' }, target: { entity_type: 'COMPONENT', name: 'PaymentGateway' },
    relationship: 'DEPENDS_ON', action: 'ONLY', scope: { type: 'PROJECT', value: null }, is_exception: false } } };

function mockRuleRequests(t: TestContext, conflict = false) {
  const requests: { url: string; body: unknown }[] = [];
  t.mock.method(globalThis, 'fetch', async (url: string, options: RequestInit) => {
    requests.push({ url, body: JSON.parse(options.body as string) });
    const data = url.endsWith('/rules/generate') ? generated : url.endsWith('/rules/check-conflicts')
      ? { has_conflict: conflict, duplicate: false, conflicts: conflict ? [{ existing_rule_id: 'CUSTOM_002', reason: 'Opposing actions' }] : [] }
      : { approved: true, rule_id: 'CUSTOM_001', conflicts_confirmed: conflict, duplicate: false };
    return new Response(JSON.stringify(data), { headers: { 'Content-Type': 'application/json' } });
  });
  return requests;
}

test('successful backend approvals update the shared display cache without a listing API', async t => {
  const requests = mockRuleRequests(t), host = await panel(t);
  await host.receive({ type: 'generate', requirement: 'Only PaymentService may depend on PaymentGateway.' });
  assert.ok(host.allMessages.some(item => item.type === 'generationStarted'));
  await host.receive({ type: 'approve' });
  const catalog = host.allMessages.filter(item => item.type === 'approvedRules').at(-1)?.rules as { rule_id: string }[];
  assert.equal(catalog[0].rule_id, 'CUSTOM_001');
  assert.equal(host.invalidations(), 1);
  assert.deepEqual(requests.map(item => new URL(item.url).pathname), ['/rules/generate', '/rules/check-conflicts', '/rules/approve']);
  host.configureMode('developer');
  assert.equal(host.remembered.size, 1);
  host.configureBackend('https://other.example');
  assert.deepEqual(JSON.parse(JSON.stringify(host.allMessages.filter(item => item.type === 'approvedRules').at(-1)?.rules)), []);
});

for (const confirmed of [true, false]) {
  test('product conflict confirmation stays inside the existing workflow: ' + confirmed, async t => {
    const requests = mockRuleRequests(t, true), host = await panel(t);
    await host.receive({ type: 'generate', requirement: 'Deny access.' });
    const conflicted = host.nextType('conflicts');
    const pending = host.receive({ type: 'approve' });
    await conflicted;
    await host.receive({ type: 'confirmConflict', confirmed });
    await pending;
    assert.equal(host.nativeConfirmations(), 0);
    const saved = requests.filter(item => item.url.endsWith('/rules/approve'));
    assert.equal(saved.length, confirmed ? 1 : 0);
    if (confirmed) { assert.equal((saved[0].body as { confirm_conflicts: boolean }).confirm_conflicts, true); }
    else { assert.equal(host.remembered.size, 0); }
  });
}

test('developer conflict confirmation still uses the native modal', async t => {
  mockRuleRequests(t, true); const host = await panel(t, 'developer');
  await host.receive({ type: 'generate', requirement: 'Deny access.' });
  await host.receive({ type: 'approve' });
  assert.equal(host.nativeConfirmations(), 1);
});

test('switching modes while awaiting inline confirmation cancels without saving', async t => {
  const requests = mockRuleRequests(t, true), host = await panel(t);
  await host.receive({ type: 'generate', requirement: 'Deny access.' });
  const conflicted = host.nextType('conflicts'), pending = host.receive({ type: 'approve' });
  await conflicted; host.configureMode('developer'); await pending;
  assert.ok(host.allMessages.some(item => item.type === 'cancelled'));
  assert.equal(requests.filter(item => item.url.endsWith('/rules/approve')).length, 0);
});
