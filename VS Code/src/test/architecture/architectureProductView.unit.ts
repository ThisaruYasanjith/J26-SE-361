import * as assert from 'node:assert/strict';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';
import { productFormHtml, productStyles, productWebviewScript } from '../../architecture/architectureProductView';
import { violationSummary } from '../../architecture/architecturePresentation';
import { conformanceResponse, exampleViolation } from './conformanceFixtures';
import { groupViolations } from '../../architecture/violationGrouping';
import { ruleWebviewScript } from '../../architecture/architectureView';
import { ProjectAnalysisWorkflow } from '../../architecture/analysisWorkflow';
import { ProjectContextSyncWorkflow } from '../../architecture/contextSyncWorkflow';
import { ConformanceWorkflow } from '../../architecture/conformanceWorkflow';

class Element {
  textContent = ''; value = ''; className = ''; hidden = false; disabled = false; type = ''; focused = false;
  scrollTop = 0; scrollHeight = 100;
  children: Element[] = [];
  listeners = new Map<string, (event: unknown) => void>();
  constructor(readonly tag = 'div') {}
  set innerHTML(_value: string) { throw new Error('Untrusted HTML insertion'); }
  append(...items: Element[]) { this.children.push(...items); }
  replaceChildren() { this.children = []; }
  focus() { this.focused = true; }
  addEventListener(name: string, callback: (event: unknown) => void) { this.listeners.set(name, callback); }
  fire(name: string, event = {}) { if (!this.disabled) { this.listeners.get(name)?.({ preventDefault() {}, ...event }); } }
}
function descendants(item: Element): Element[] { return [item, ...item.children.flatMap(descendants)]; }
function text(item: Element): string { return descendants(item).map(node => node.textContent).join('\n'); }
function view(includeDeveloper = false) {
  const elements = new Map<string, Element>();
  const element = (id: string) => {
    if (!elements.has(id)) { elements.set(id, new Element()); }
    return elements.get(id)!;
  };
  const sent: Record<string, unknown>[] = [];
  const receivers: ((event: unknown) => void)[] = [];
  const api = { postMessage: (message: unknown) => sent.push(JSON.parse(JSON.stringify(message))) };
  runInNewContext(includeDeveloper ? ruleWebviewScript + productWebviewScript : productWebviewScript, {
    document: { getElementById: element, createElement: (tag: string) => new Element(tag) },
    window: { addEventListener: (_name: string, callback: (event: unknown) => void) => { receivers.push(callback); } },
    vscode: api, acquireVsCodeApi: () => api,
  });
  if (includeDeveloper) { assert.deepEqual(sent.shift(), { type: 'ready' }); }
  return { element, sent, receive: (data: unknown) => { for (const receive of receivers) { receive({ data }); } },
    button: (label: string) => descendants(element('product-conversation')).find(item => item.tag === 'button' && item.textContent === label)! };
}
const envelope = { status: 'VALID', reason_code: null, rule: {
  rule_type: 'COMPONENT_ACCESS', source: { entity_type: 'COMPONENT', name: 'PaymentService' }, relationship: 'DEPENDS_ON',
  target: { entity_type: 'COMPONENT', name: 'PaymentGateway' }, action: 'ONLY', scope: { type: 'PROJECT', value: null }, is_exception: false,
} };
const proposal = { type: 'proposal', response: { json_valid: true, schema_valid: true, rule: envelope, validation_errors: [], generated_text: 'private raw JSON' }, canApprove: true };
function checked(violations = [exampleViolation]) {
  const result = conformanceResponse(violations);
  return { type: 'conformance', state: { status: 'checked', result, navigableViolationIds: violations.map(item => item.violation_id) },
    displaySummary: violationSummary(result), canCheck: true, checking: false };
}

test('product markup has two internal views, a compact initial state, and no graph or raw output', () => {
  assert.match(productFormHtml, /id="product-violations" hidden/);
  assert.match(productFormHtml, /No project analyzed/);
  assert.match(productFormHtml, /Not checked/);
  assert.match(productFormHtml, /No project-specific architecture rules have been added here yet/);
  assert.match(productFormHtml, /Ctrl\+Enter/);
  assert.match(productFormHtml, /id="product-view-violations" type="button"/);
  assert.match(productFormHtml, /id="product-back" class="secondary"/);
  assert.doesNotMatch(productFormHtml, /<select|<svg|<canvas|<pre|<script|https:\/\//);
});

test('switching UI modes toggles the existing views without requests or lost conversation', () => {
  const host = view(); host.receive(proposal);
  const before = text(host.element('product-conversation'));
  host.receive({ type: 'uiMode', mode: 'developer' });
  assert.ok(host.element('product-ui').hidden);
  assert.equal(host.element('developer-ui').hidden, false);
  host.receive({ type: 'uiMode', mode: 'product' });
  assert.equal(host.element('product-ui').hidden, false);
  assert.equal(text(host.element('product-conversation')), before);
  assert.deepEqual(host.sent, []);
});

test('analyzed and synchronized states guide the next project action without internal paths', () => {
  const host = view();
  host.receive({ type: 'analysis', state: { status: 'succeeded', summary: { projectName: '<payments>', contextPath: '/private/context.json' } } });
  assert.equal(host.element('product-project-name').textContent, '<payments>');
  assert.equal(host.element('product-analysis').textContent, 'Complete');
  assert.match(host.element('product-analysis').className, /badge-success/);
  assert.equal(host.element('product-scan').className, 'secondary');
  host.receive({ type: 'contextSync', state: { status: 'not-synchronized' }, canSync: true, syncing: false });
  assert.equal(host.element('product-sync-action').className, '');
  host.receive({ type: 'contextSync', state: { status: 'synchronized' }, canSync: true, syncing: false });
  assert.equal(host.element('product-sync').textContent, 'Synchronized');
  assert.match(host.element('product-sync').className, /badge-success/);
  assert.doesNotMatch(host.element('product-project-notice').textContent, /private|context.json/);
});

test('analysis, sync, and checking actions keep the existing message protocol', () => {
  for (const [id, type] of [['scan', 'scan'], ['sync-action', 'sync'], ['check', 'checkConformance']]) {
    const host = view();
    host.receive({ type: 'contextSync', state: { status: 'not-synchronized' }, canSync: true, syncing: false });
    host.receive({ type: 'conformance', state: { status: 'idle' }, canCheck: true, checking: false });
    host.element('product-' + id).fire('click');
    assert.deepEqual(host.sent, [{ type }]);
  }
});

test('approved cards use confirmed envelopes, show exceptions only when relevant, and support empty state', () => {
  const host = view(); host.receive({ type: 'approvedRules', rules: [] });
  assert.equal(host.element('product-approved-count').textContent, '0');
  assert.match(text(host.element('product-approved-list')), /No project-specific/);
  host.receive({ type: 'approvedRules', rules: [{ ...envelope, rule_id: 'CUSTOM_001' }] });
  const card = text(host.element('product-approved-list'));
  for (const value of ['PaymentService', 'PaymentGateway', 'ONLY', 'CUSTOM_001', 'COMPONENT_ACCESS']) { assert.ok(card.includes(value)); }
  assert.doesNotMatch(card, /Exception|entity_type|schema_valid/);
  host.receive({ type: 'approvedRules', rules: [{ ...envelope, rule_id: 'CUSTOM_002', rule: { ...envelope.rule, is_exception: true } }] });
  assert.match(text(host.element('product-approved-list')), /Exception/);
});

test('submitting a requirement shows the actual user message and a loading response when accepted by the host', () => {
  const host = view(); host.element('product-requirement').value = '  Only PaymentService may depend on PaymentGateway.  ';
  host.element('product-rule-form').fire('submit');
  assert.deepEqual(host.sent, [{ type: 'generate', requirement: 'Only PaymentService may depend on PaymentGateway.' }]);
  host.receive({ type: 'generationStarted', requirement: '<img src=x onerror=alert(1)>' });
  const chat = text(host.element('product-conversation'));
  assert.match(chat, /You/); assert.match(chat, /<img src=x onerror=alert\(1\)>/);
  assert.match(chat, /Interpreting architecture requirement/);
  assert.ok(host.element('product-generate').disabled);
});

test('blank input sends nothing and ordinary Enter preserves multiline composition', () => {
  const host = view(); host.element('product-rule-form').fire('submit');
  assert.deepEqual(host.sent, []);
  host.element('product-requirement').value = 'Deny access.';
  host.element('product-requirement').fire('keydown', { key: 'Enter' });
  assert.deepEqual(host.sent, []);
  host.element('product-requirement').fire('keydown', { key: 'Enter', ctrlKey: true });
  assert.deepEqual(host.sent, [{ type: 'generate', requirement: 'Deny access.' }]);
});

test('VALID interpretation displays fields, hides raw JSON, and approval remains a separate action', () => {
  const host = view(); host.receive(proposal);
  const chat = text(host.element('product-conversation'));
  for (const value of ['ONLY', 'PaymentService', 'DEPENDS_ON', 'PaymentGateway', 'Project', 'Approve Rule', 'Cancel']) { assert.ok(chat.includes(value)); }
  assert.doesNotMatch(chat, /private raw JSON/);
  assert.deepEqual(host.sent, []);
  host.button('Approve Rule').fire('click');
  assert.deepEqual(host.sent, [{ type: 'approve' }]);
});

for (const status of ['AMBIGUOUS', 'UNSUPPORTED']) {
  test(status + ' uses the reason meaning and never offers approval', () => {
    const host = view();
    host.receive({ ...proposal, canApprove: false, response: { ...proposal.response, rule: { status, rule: null, reason_code: 'MISSING_TARGET' } } });
    assert.match(text(host.element('product-conversation')), /Specify the target/);
    assert.ok(text(host.element('product-conversation')).includes(status));
    assert.equal(host.button('Approve Rule'), undefined);
  });
}

test('schema-invalid interpretations cannot be approved or expose raw output', () => {
  const host = view(); host.receive({ ...proposal, canApprove: false, response: { ...proposal.response, schema_valid: false } });
  assert.match(text(host.element('product-conversation')), /could not be validated/);
  assert.equal(host.button('Approve Rule'), undefined);
  assert.doesNotMatch(text(host.element('product-conversation')), /private raw JSON/);
});

test('cancel and edits retire all previous proposal actions', () => {
  const host = view(); host.receive(proposal);
  const approve = host.button('Approve Rule'); host.button('Cancel').fire('click'); approve.fire('click');
  assert.deepEqual(host.sent, [{ type: 'edit' }]);
  const other = view(); other.receive(proposal); other.element('product-requirement').fire('input');
  assert.ok(other.button('Approve Rule').disabled);
  assert.deepEqual(other.sent, [{ type: 'edit' }]);
});

for (const confirmed of [true, false]) {
  test('conflict action sends an explicit decision: ' + confirmed, () => {
    const host = view(); host.receive(proposal); host.receive({ type: 'busy', busy: true });
    host.receive({ type: 'conflicts', confirmationRequired: true, conflicts: { conflicts: [{ existing_rule_id: '<CUSTOM_002>', reason: '<deny relationship>' }] } });
    assert.match(text(host.element('product-conversation')), /<CUSTOM_002>/);
    assert.match(text(host.element('product-conversation')), /<deny relationship>/);
    // The active conflict decision remains available while the host is awaiting confirmation.
    const buttons = descendants(host.element('product-conversation')).filter(item => item.tag === 'button' && !item.disabled);
    buttons.find(item => item.textContent === (confirmed ? 'Approve Anyway' : 'Cancel'))!.fire('click');
    assert.deepEqual(host.sent, [{ type: 'confirmConflict', confirmed }]);
    assert.ok(buttons.every(item => item.disabled));
  });
}

test('approval, duplicate and error responses are clear and preserve untrusted text as text', () => {
  const host = view(); host.receive(proposal);
  host.receive({ type: 'approved', approval: { duplicate: false, rule_id: 'CUSTOM_001' } });
  assert.match(text(host.element('product-conversation')), /Rule approved and added/);
  host.receive({ type: 'approved', approval: { duplicate: true, rule_id: 'CUSTOM_001' } });
  assert.match(text(host.element('product-conversation')), /already approved.*CUSTOM_001/);
  host.receive({ type: 'error', canApprove: false, message: '<backend unavailable>' });
  assert.match(text(host.element('product-conversation')), /<backend unavailable>/);
});

test('cancelled confirmations allow another review while changed context invalidates approval', () => {
  const host = view(); host.receive(proposal);
  host.receive({ type: 'cancelled', canApprove: true });
  const buttons = descendants(host.element('product-conversation')).filter(item => item.tag === 'button' && !item.disabled);
  assert.ok(buttons.some(item => item.textContent === 'Approve Rule'));
  host.receive({ type: 'contextChanged' });
  assert.ok(buttons.every(item => item.disabled));
  assert.match(host.element('product-rule-notice').textContent, /Generate a new interpretation/);
});

test('View Violations and Back to Configuration are local navigation with no requests', () => {
  const host = view(); host.receive(proposal);
  host.element('product-view-violations').fire('click');
  assert.ok(host.element('product-configuration').hidden);
  assert.equal(host.element('product-violations').hidden, false);
  host.element('product-back').fire('click');
  assert.equal(host.element('product-configuration').hidden, false);
  assert.equal(host.button('Approve Rule').disabled, false);
  assert.deepEqual(host.sent, []);
});

test('unchecked conformance is neutral rather than a confirmed zero', () => {
  const host = view(); host.receive({ type: 'conformance', state: { status: 'idle' }, canCheck: false, checking: false });
  assert.equal(host.element('product-count').textContent, 'Not checked');
  assert.equal(host.element('product-total').textContent, '—');
  assert.match(host.element('product-conformance-state').textContent, /has not been checked/);
});

test('summary cards show total, dependency and structure counts from the display classification', () => {
  const host = view(); const placement = { ...exampleViolation, violation_id: 'PLACEMENT', relationship: 'LOCATED_IN' as const, rule_id: 'PLACEMENT_RULE' };
  host.receive(checked([exampleViolation, placement]));
  assert.equal(host.element('product-total').textContent, '2');
  assert.equal(host.element('product-dependency').textContent, '1');
  assert.equal(host.element('product-structure').textContent, '1');
  assert.equal(host.element('product-count').textContent, '2');
  assert.match(host.element('product-count').className, /badge-error/);
  assert.equal(host.element('product-total').className, 'count-positive');
  assert.equal(host.element('product-structure').className, 'count-positive');
});

test('conformant state shows the success empty state', () => {
  const host = view(); host.receive(checked([]));
  assert.equal(host.element('product-count').textContent, '0');
  assert.match(host.element('product-count').className, /badge-success/);
  assert.equal(host.element('product-total').className, 'count-zero');
  assert.match(text(host.element('product-findings')), /No architecture violations detected/);
});

test('current-file findings precede other findings, preserve origins, and use existing navigation IDs', () => {
  const host = view();
  const other = { ...exampleViolation, violation_id: 'OTHER', file_path: 'src/Other.java', rule_id: 'CUSTOM_001' };
  const data = checked([exampleViolation, other]);
  const activeFile = { fileName: 'Example.java', filePath: 'src/Example.java' };
  host.receive({ ...data, activeFile, violationGroups: groupViolations(data.state.result.violations, activeFile) });
  const sections = host.element('product-findings').children;
  assert.match(text(sections[0]), /Current File Violations — Example.java/);
  assert.match(text(sections[0]), /Base Rule/);
  assert.match(text(sections[1]), /Other Project Violations \(1\)/);
  assert.match(text(sections[1]), /Custom Rule/);
  assert.equal(descendants(host.element('product-findings')).filter(item => item.textContent === exampleViolation.message).length, 2);
  const open = descendants(sections[0]).find(item => item.textContent === 'Open Source')!; open.fire('click');
  assert.deepEqual(host.sent, [{ type: 'openViolation', violationId: exampleViolation.violation_id }]);
});

test('clean active files and project-wide fallback use cached groups without requests', () => {
  const host = view(), data = checked();
  const activeFile = { fileName: 'Clean.java', filePath: 'src/Clean.java' };
  host.receive({ ...data, activeFile, violationGroups: groupViolations(data.state.result.violations, activeFile) });
  assert.match(text(host.element('product-findings').children[0]), /No architecture violations in this file/);
  host.receive(data);
  assert.match(text(host.element('product-findings')), /Project Violations/);
  assert.doesNotMatch(text(host.element('product-findings')), /Current File Violations/);
  assert.deepEqual(host.sent, []);
});

for (const status of ['stale', 'checking', 'failed', 'cancelled']) {
  test(status + ' clears old counts and findings instead of claiming conformance', () => {
    const host = view(); host.receive(checked([]));
    host.receive({ type: 'conformance', state: { status, message: 'Refresh required.' }, canCheck: true, checking: status === 'checking' });
    assert.equal(host.element('product-total').textContent, '—');
    assert.equal(host.element('product-total').className, '');
    assert.doesNotMatch(text(host.element('product-findings')), /No architecture violations detected/);
    assert.match(host.element('product-conformance-state').textContent.toLowerCase(), new RegExp(status === 'checking' ? 'checking' : status));
  });
}

test('product layout wraps at narrow widths and uses theme variables', () => {
  assert.match(productStyles, /@media \(max-width: 440px\)/);
  assert.match(productStyles, /minmax\(0, 1fr\)/);
  assert.match(productStyles, /flex-wrap: wrap/);
  assert.match(productStyles, /--vscode-editor-background/);
  assert.match(productStyles, /color-mix\(in srgb/);
  assert.match(productStyles, /button:active:enabled/);
  assert.match(productStyles, /button\.secondary:active:enabled/);
  assert.match(productStyles, /button:focus-visible/);
  assert.match(productStyles, /appearance: none/);
  assert.doesNotMatch(productStyles, /#[0-9a-fA-F]{3,8}\b|https?:\/\//);
});

for (const customRules of [false, true]) {
  test('both UIs enable conformance after analysis/sync and re-sync, independent of chat; custom rules: ' + customRules, async t => {
    const host = view(true);
    const summary = { projectName: 'payments', projectRoot: '/payments', contextPath: '/payments/.architecture/project_context.json', componentCount: 1, relationshipCount: 0 };
    const analysis = new ProjectAnalysisWorkflow({ analyze: async () => summary }, {
      folders: () => [{ name: 'payments', fsPath: '/payments', scheme: 'file' }], choose: async folders => folders[0],
      progress: task => task(), showError() {},
    });
    const logger = { appendLine() {} };
    const sync = new ProjectContextSyncWorkflow(analysis, {
      baseUrl: 'https://backend.example', syncProjectContext: async () => ({ updated: true, project_name: 'payments', components: 1, relationships: 0, rag_invalidated: true }),
    }, logger, async () => ({ schema_version: '1.0', project_name: 'payments', project_root: '.', components: [{}], relationships: [] }));
    let checks = 0;
    const violations = customRules ? [{ ...exampleViolation, rule_id: 'CUSTOM_001' }] : [exampleViolation];
    const conformance = new ConformanceWorkflow(analysis, sync, {
      baseUrl: 'https://backend.example', checkConformance: async () => { checks++; return conformanceResponse(violations); },
    }, { clear() {}, prepare: async () => [], replace() {}, open: async () => false }, logger);
    const sendConformance = () => host.receive({ type: 'conformance', state: conformance.state,
      canCheck: conformance.canCheck, checking: conformance.isRunning,
      displaySummary: conformance.state.status === 'checked' ? violationSummary(conformance.state.result) : undefined });
    const sendSync = () => host.receive({ type: 'contextSync', state: sync.state, canSync: sync.canSync, syncing: sync.isRunning });
    analysis.subscribe(state => host.receive({ type: 'analysis', state }));
    conformance.subscribe(sendConformance);
    let previousSync = sync.state;
    sync.subscribe(state => {
      if (state.status === 'synchronized' && state !== previousSync) { host.receive({ type: 'contextChanged' }); }
      previousSync = state; sendSync();
    });
    t.after(() => { conformance.dispose(); sync.dispose(); analysis.dispose(); });
    const expectEnabled = (enabled: boolean) => {
      assert.equal(host.element('product-check').disabled, !enabled, 'product eligibility');
      assert.equal(host.element('check-conformance').disabled, !enabled, 'developer eligibility');
    };
    sendConformance(); sendSync();
    expectEnabled(false);
    await analysis.run(); expectEnabled(false);
    host.receive({ type: 'approvedRules', rules: customRules ? [{ ...envelope, rule_id: 'CUSTOM_001' }] : [] });
    const cachedRules = text(host.element('product-approved-list'));
    await sync.run(); expectEnabled(true);
    assert.equal(checks, 0, 'sync never runs conformance implicitly');
    // A pending generation and its later interpretation must not gate conformance in either UI.
    host.receive({ type: 'busy', busy: true });
    host.receive({ type: 'generationStarted', requirement: 'Only PaymentService may depend on PaymentGateway.' });
    expectEnabled(true);
    host.element('check-conformance').fire('click');
    assert.deepEqual(host.sent.at(-1), { type: 'checkConformance' });
    await conformance.run(); expectEnabled(true);
    host.receive(proposal); expectEnabled(true);
    host.receive({ type: 'approved', approval: { duplicate: true, rule_id: 'CUSTOM_001' } });
    host.receive({ type: 'busy', busy: false }); expectEnabled(true);
    await analysis.run(); expectEnabled(false);
    assert.equal(sync.state.status, 'not-synchronized');
    assert.equal(conformance.state.status, 'stale');
    assert.equal(host.element('violation-list').children.length, 0);
    // No generation/proposal/approval message occurs between re-analysis, re-sync and the next check.
    await sync.run(); expectEnabled(true);
    assert.equal(conformance.state.status, 'stale');
    assert.equal(text(host.element('product-approved-list')), cachedRules);
    host.receive({ type: 'uiMode', mode: 'developer' }); expectEnabled(true);
    host.receive({ type: 'uiMode', mode: 'product' }); expectEnabled(true);
    host.element('product-check').fire('click');
    assert.deepEqual(host.sent.at(-1), { type: 'checkConformance' });
    const pendingCheck = conformance.run();
    expectEnabled(false);
    await pendingCheck; expectEnabled(true);
    assert.equal(checks, 2);
  });
}
