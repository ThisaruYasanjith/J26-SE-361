import * as assert from 'node:assert/strict';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';
import { analysisFormHtml, architectureStyles, conformanceFormHtml, ruleFormHtml, ruleWebviewScript } from '../../architecture/architectureView';
import { conformanceResponse, exampleViolation } from './conformanceFixtures';
import { ActiveJavaFile, groupViolations } from '../../architecture/violationGrouping';

class Element {
  textContent = '';
  disabled = false;
  hidden = false;
  value = '';
  className = '';
  children: Element[] = [];
  listeners = new Map<string, (event: unknown) => void>();
  set innerHTML(_value: string) { throw new Error('Backend text must not be inserted as HTML'); }
  replaceChildren() { this.children = []; }
  append(...items: Element[]) { this.children.push(...items); }
  addEventListener(name: string, callback: (event: unknown) => void) { this.listeners.set(name, callback); }
  fire(name: string) { this.listeners.get(name)?.({ preventDefault() {} }); }
}
function view() {
  const elements = new Map<string, Element>();
  const element = (id: string) => {
    if (!elements.has(id)) { elements.set(id, new Element()); }
    return elements.get(id)!;
  };
  const sent: Record<string, unknown>[] = [];
  let receive: (event: unknown) => void = () => {};
  runInNewContext(ruleWebviewScript, {
    document: { getElementById: element, createElement: () => new Element() },
    window: { addEventListener: (_name: string, callback: typeof receive) => { receive = callback; } },
    acquireVsCodeApi: () => ({ postMessage: (message: unknown) => sent.push(JSON.parse(JSON.stringify(message))) }),
  });
  assert.deepEqual(sent.shift(), { type: 'ready' });
  return { element, sent, receive: (data: unknown) => receive({ data }) };
}
const response = {
  json_valid: true, schema_valid: true, validation_errors: [], generated_text: 'raw model output',
  rule: { status: 'VALID', reason_code: null, rule: {
    rule_type: 'COMPONENT_ACCESS', source: { entity_type: 'COMPONENT', name: '<img src=x onerror=alert(1)>' },
    relationship: 'DEPENDS_ON', target: { entity_type: 'COMPONENT', name: 'PaymentGateway' }, action: 'ONLY',
    scope: { type: 'PROJECT', value: null }, is_exception: false,
  } },
};
test('webview rejects blank input and trims a valid submission', () => {
  const { element, sent } = view();
  element('requirement').value = ' \n ';
  element('rule-form').fire('submit');
  assert.equal(sent.length, 0);
  assert.match(element('rule-status').textContent, /Enter an architecture rule/);
  element('requirement').value = ' Only PaymentService may depend on PaymentGateway. ';
  element('rule-form').fire('submit');
  assert.deepEqual(sent, [{ type: 'generate', requirement: 'Only PaymentService may depend on PaymentGateway.' }]);
  assert.ok(element('generate').disabled && element('requirement').disabled);
});
test('webview displays every rule field as text and requires a separate approval click', () => {
  const { element, receive, sent } = view();
  receive({ type: 'proposal', response, canApprove: true });
  const text = element('interpretation').children.map(item => item.textContent).join('\n');
  for (const label of ['Status', 'Rule type', 'Source', 'Relationship', 'Target', 'Action', 'Scope', 'Exception']) {
    assert.ok(text.includes(label));
  }
  assert.ok(text.includes('<img src=x onerror=alert(1)>'));
  assert.equal(element('generated-text').textContent, 'raw model output');
  assert.equal(sent.length, 0);
  assert.equal(element('approve').disabled, false);
  element('approve').fire('click');
  assert.deepEqual(sent, [{ type: 'approve' }]);
});
test('webview shows uncertainty, reason codes and separate validation messages', () => {
  const { element, receive } = view();
  receive({ type: 'proposal', response: { ...response, rule: { status: 'AMBIGUOUS', rule: null, reason_code: 'MISSING_TARGET' },
    validation_errors: [{ path: 'rule', message: 'First problem' }, { path: 'status', message: 'Second problem' }] }, canApprove: false });
  assert.ok(element('interpretation').children.some(item => item.textContent === 'MISSING_TARGET'));
  assert.equal(element('validation-errors').textContent, 'rule: First problem\nstatus: Second problem');
  assert.equal(element('approve').disabled, true);
});
test('editing removes the stale approval action and notifies the host', () => {
  const { element, receive, sent } = view();
  receive({ type: 'proposal', response, canApprove: true });
  element('requirement').fire('input');
  assert.equal(element('approve').disabled, true);
  assert.equal(element('interpretation').children.length, 0);
  assert.deepEqual(sent, [{ type: 'edit' }]);
});
test('conflict cancellation leaves the rule unapproved and can be retried', () => {
  const { element, receive } = view();
  receive({ type: 'conflicts', conflicts: { conflicts: [{ existing_rule_id: 'CUSTOM_001', reason: 'ONLY restriction' }] } });
  receive({ type: 'cancelled', canApprove: true });
  assert.equal(element('conflicts').children[0].children[0].textContent, 'CUSTOM_001');
  assert.equal(element('conflicts').children[0].children[1].textContent, 'ONLY restriction');
  assert.match(element('rule-status').textContent, /has not been approved/);
  assert.equal(element('approve').disabled, false);
});
test('duplicate approval gives a clear success message and disables saving', () => {
  const { element, receive } = view();
  receive({ type: 'approved', approval: { duplicate: true, rule_id: 'CUSTOM_001' } });
  assert.match(element('rule-status').textContent, /Already approved as CUSTOM_001/);
  assert.equal(element('approve').disabled, true);
});
test('scan button requests analysis without sending a directory from the webview', () => {
  const { element, sent } = view();
  element('scan').fire('click');
  assert.deepEqual(sent, [{ type: 'scan' }]);
  assert.ok(element('scan').disabled && element('generate').disabled);
});
test('scan summary displays real project metadata and context path as text', () => {
  const { element, receive } = view();
  receive({ type: 'analysis', state: { status: 'succeeded', summary: {
    projectName: 'payments', componentCount: 7, relationshipCount: 15, contextPath: '/project/.architecture/project_context.json',
  } } });
  const text = element('scan-summary').children.map(item => item.textContent).join('\n');
  for (const value of ['payments', '7', '15', '/project/.architecture/project_context.json']) { assert.ok(text.includes(value)); }
  assert.match(element('scan-status').textContent, /scan complete/);
  assert.equal(element('scan').disabled, false);
});
test('cancelled scan clears progress and leaves the existing AI proposal available', () => {
  const { element, receive } = view();
  receive({ type: 'proposal', response, canApprove: true });
  receive({ type: 'analysis', state: { status: 'running' } });
  assert.equal(element('approve').disabled, true);
  receive({ type: 'analysis', state: { status: 'cancelled' } });
  assert.match(element('scan-status').textContent, /cancelled/);
  assert.equal(element('approve').disabled, false);
});

test('sync is explicit, disabled before scanning, and sends no context or paths from the webview', () => {
  const { element, receive, sent } = view();
  receive({ type: 'contextSync', state: { status: 'not-synchronized' }, canSync: false, syncing: false });
  assert.ok(element('sync').disabled);
  element('sync').fire('click');
  assert.equal(sent.length, 0);
  receive({ type: 'contextSync', state: { status: 'not-synchronized' }, canSync: true, syncing: false });
  assert.equal(sent.length, 0);
  element('sync').fire('click');
  assert.deepEqual(sent, [{ type: 'sync' }]);
  assert.ok(element('sync').disabled && element('scan').disabled && element('generate').disabled);
});

test('sync failure preserves scan summary and shows an independent retryable status', () => {
  const { element, receive } = view();
  receive({ type: 'analysis', state: { status: 'succeeded', summary: {
    projectName: 'payments', componentCount: 7, relationshipCount: 15, contextPath: '/project/.architecture/project_context.json',
  } } });
  const summary = element('scan-summary').children.map(item => item.textContent);
  receive({ type: 'contextSync', state: { status: 'failed', message: 'Cannot reach backend.' }, canSync: true, syncing: false });
  assert.match(element('sync-status').textContent, /AI context: not synchronized.*Cannot reach backend/);
  assert.match(element('scan-status').textContent, /scan complete/);
  assert.deepEqual(element('scan-summary').children.map(item => item.textContent), summary);
  assert.equal(element('sync').disabled, false);
});

test('successful sync reports backend metadata and clears a stale rule interpretation', () => {
  const { element, receive } = view();
  receive({ type: 'proposal', response, canApprove: true });
  receive({ type: 'contextSync', state: { status: 'synchronized', response: {
    project_name: 'payments', components: 7, relationships: 15,
  } }, canSync: true, syncing: false });
  receive({ type: 'contextChanged' });
  assert.match(element('sync-status').textContent, /AI context: synchronized.*payments: 7 components, 15 relationships/);
  assert.ok(element('approve').disabled);
  assert.equal(element('interpretation').children.length, 0);
  assert.equal(element('generate').disabled, false);
});

test('conformance starts not checked and requires a synchronized context to enable its action', () => {
  const { element, receive, sent } = view();
  receive({ type: 'conformance', state: { status: 'not-checked' }, checking: false, canCheck: false });
  assert.match(element('conformance-status').textContent, /not checked/);
  assert.equal(element('check-conformance').disabled, true);
  element('check-conformance').fire('click');
  assert.equal(sent.length, 0);
  receive({ type: 'conformance', state: { status: 'not-checked' }, checking: false, canCheck: true });
  element('check-conformance').fire('click');
  assert.deepEqual(sent, [{ type: 'checkConformance' }]);
  assert.match(element('conformance-status').textContent, /checking/);
  assert.ok(element('check-conformance').disabled && element('generate').disabled);
});
test('checking and conformant states show an independent summary without touching AI status', () => {
  const { element, receive } = view();
  receive({ type: 'proposal', response, canApprove: true });
  const aiStatus = element('rule-status').textContent;
  receive({ type: 'conformance', state: { status: 'checking' }, checking: true, canCheck: false });
  assert.match(element('conformance-status').textContent, /checking/);
  receive({ type: 'conformance', state: { status: 'checked', result: conformanceResponse([]), navigableViolationIds: [] }, checking: false, canCheck: true });
  assert.match(element('conformance-status').textContent, /passed \(conformant\)/);
  assert.equal(element('violation-list').children.length, 0);
  const text = element('conformance-summary').children.map(child => child.textContent).join('\n');
  for (const value of ['Conformant', 'true', 'Total violations', 'Base rule violations', 'Custom rule violations', '0']) { assert.ok(text.includes(value)); }
  assert.equal(element('rule-status').textContent, aiStatus);
});
test('violation cards show backend fields as text and navigate using only a violation ID', () => {
  const { element, receive, sent } = view();
  const violation = { ...exampleViolation, message: '<img src=x onerror=alert(1)>' };
  receive({ type: 'conformance', state: { status: 'checked', result: conformanceResponse([violation]),
    navigableViolationIds: [violation.violation_id] }, checking: false, canCheck: true });
  assert.match(element('conformance-status').textContent, /violations found/);
  const card = element('violation-list').children[0];
  const button = card.children[0];
  assert.equal(button.textContent, 'ERROR: <img src=x onerror=alert(1)>');
  const text = card.children[1].children.map(child => child.textContent).join('\n');
  for (const value of [violation.source, violation.target!, violation.relationship!, violation.rule_id, 'BASE', 'COMPONENT_ACCESS']) {
    assert.ok(text.includes(value));
  }
  button.fire('click');
  assert.deepEqual(sent, [{ type: 'openViolation', violationId: violation.violation_id }]);
});
test('findings with unavailable files remain visible with navigation disabled', () => {
  const { element, receive, sent } = view();
  receive({ type: 'conformance', state: { status: 'checked', result: conformanceResponse(), navigableViolationIds: [] }, checking: false, canCheck: true });
  const card = element('violation-list').children[0];
  assert.ok(card.children[0].disabled);
  card.children[0].fire('click');
  assert.equal(sent.length, 0);
  assert.ok(card.children[1].children.some(child => child.textContent.includes('unavailable')));
});
test('stale, failed and cleared conformance states remove old findings without hiding scan results', () => {
  const { element, receive, sent } = view();
  receive({ type: 'analysis', state: { status: 'succeeded', summary: { projectName: 'payments', componentCount: 7,
    relationshipCount: 15, contextPath: '/project/.architecture/project_context.json' } } });
  receive({ type: 'conformance', state: { status: 'checked', result: conformanceResponse(), navigableViolationIds: [] }, checking: false, canCheck: true });
  receive({ type: 'conformance', state: { status: 'stale', message: 'Re-analyzed. Sync again.' }, checking: false, canCheck: false });
  assert.match(element('conformance-status').textContent, /stale \/ not checked/);
  assert.equal(element('violation-list').children.length, 0);
  assert.match(element('scan-status').textContent, /scan complete/);
  receive({ type: 'conformance', state: { status: 'failed', message: 'Backend unavailable.' }, checking: false, canCheck: true });
  assert.match(element('conformance-status').textContent, /check failed.*Backend unavailable/);
  element('clear-conformance').fire('click');
  assert.deepEqual(sent, [{ type: 'clearConformance' }]);
});

function groupedMessage(result = conformanceResponse(), activeFile?: ActiveJavaFile) {
  return { type: 'conformance', state: { status: 'checked', result,
    navigableViolationIds: result.violations.map(item => item.violation_id) }, checking: false, canCheck: true,
    activeFile, violationGroups: groupViolations(result.violations, activeFile) };
}
test('current-file findings appear first with filename/count and other findings appear once below', () => {
  const { element, receive, sent } = view();
  const other = { ...exampleViolation, violation_id: 'OTHER', file_path: 'src/Other.java' };
  receive(groupedMessage(conformanceResponse([other, exampleViolation]), { filePath: 'src/Example.java', fileName: 'Example.java' }));
  const sections = element('violation-list').children;
  assert.equal(sections.length, 2);
  assert.equal(sections[0].children[0].textContent, 'Current File Violations — Example.java (1)');
  assert.equal(sections[1].children[0].textContent, 'Other Project Violations (1)');
  assert.equal(sections[0].children.length, 2);
  assert.equal(sections[1].children.length, 2);
  sections[0].children[1].children[0].fire('click');
  sections[1].children[1].children[0].fire('click');
  assert.deepEqual(sent, [{ type: 'openViolation', violationId: exampleViolation.violation_id }, { type: 'openViolation', violationId: 'OTHER' }]);
});
test('a Java file with no findings shows a clear empty state and keeps other project findings', () => {
  const { element, receive } = view();
  receive(groupedMessage(conformanceResponse(), { filePath: 'src/Clean.java', fileName: 'Clean.java' }));
  const sections = element('violation-list').children;
  assert.equal(sections[0].children[0].textContent, 'Current File Violations — Clean.java (0)');
  assert.equal(sections[0].children[1].textContent, 'No architecture violations in this file.');
  assert.equal(sections[1].children[0].textContent, 'Other Project Violations (1)');
});
test('a conformant project with an active Java file omits the empty Other section', () => {
  const { element, receive } = view();
  receive(groupedMessage(conformanceResponse([]), { filePath: 'src/Clean.java', fileName: 'Clean.java' }));
  assert.equal(element('violation-list').children.length, 1);
  assert.match(element('conformance-status').textContent, /passed/);
});
test('switching active files reorders the cached list and preserves project-wide summary values', () => {
  const { element, receive, sent } = view();
  const other = { ...exampleViolation, violation_id: 'OTHER', file_path: 'src/Other.java' };
  const result = conformanceResponse([exampleViolation, other]);
  receive(groupedMessage(result, { filePath: 'src/Example.java', fileName: 'Example.java' }));
  const summary = element('conformance-summary').children.map(child => child.textContent);
  receive(groupedMessage(result, { filePath: 'src/Other.java', fileName: 'Other.java' }));
  const current = element('violation-list').children[0];
  assert.match(current.children[0].textContent, /Other.java/);
  current.children[1].children[0].fire('click');
  assert.deepEqual(sent, [{ type: 'openViolation', violationId: 'OTHER' }]);
  assert.deepEqual(element('conformance-summary').children.map(child => child.textContent), summary);
});
test('no relevant Java editor restores the original flat project-wide list', () => {
  const { element, receive, sent } = view();
  receive(groupedMessage(conformanceResponse(), { filePath: 'src/Clean.java', fileName: 'Clean.java' }));
  receive(groupedMessage());
  assert.equal(element('violation-list').children.length, 1);
  const card = element('violation-list').children[0];
  assert.equal(card.children[0].textContent, 'ERROR: ' + exampleViolation.message);
  card.children[0].fire('click');
  assert.deepEqual(sent, [{ type: 'openViolation', violationId: exampleViolation.violation_id }]);
});
test('new conformance results replace both groups instead of retaining old findings', () => {
  const { element, receive } = view();
  const active = { filePath: 'src/Example.java', fileName: 'Example.java' };
  receive(groupedMessage(conformanceResponse(), active));
  receive(groupedMessage(conformanceResponse([]), active));
  assert.equal(element('violation-list').children.length, 1);
  assert.equal(element('violation-list').children[0].children[1].textContent, 'No architecture violations in this file.');
});
test('stale results never reappear as current-file findings', () => {
  const { element, receive } = view();
  const message = groupedMessage(conformanceResponse(), { filePath: 'src/Example.java', fileName: 'Example.java' });
  receive(message);
  receive({ ...message, state: { status: 'stale', message: 'Context changed.' } });
  assert.equal(element('violation-list').children.length, 0);
  assert.match(element('conformance-status').textContent, /stale/);
});

test('initial cards have clear headings, no-project status and collapsed raw output', () => {
  assert.ok(analysisFormHtml.includes('Project Architecture') && analysisFormHtml.includes('Analysis: Not analyzed'));
  assert.ok(analysisFormHtml.includes('AI Context: Not synchronized') && analysisFormHtml.includes('Conformance: Not checked'));
  assert.ok(ruleFormHtml.includes('AI Rule Definition') && ruleFormHtml.includes('Generate Rule'));
  assert.ok(ruleFormHtml.includes('id="interpretation-card" class="interpretation-card" hidden'));
  assert.ok(ruleFormHtml.includes('<details id="raw-output" hidden>') && !ruleFormHtml.includes('<details id="raw-output" open'));
  assert.ok(conformanceFormHtml.includes('Architecture Conformance'));
});
test('project badges reflect analyzed, synchronized and deterministic conformance states', () => {
  const { element, receive } = view();
  receive({ type: 'analysis', state: { status: 'succeeded', summary: {
    projectName: 'payments', componentCount: 7, relationshipCount: 15, contextPath: '/project/context.json',
  } } });
  receive({ type: 'contextSync', state: { status: 'synchronized', response: { project_name: 'payments', components: 7, relationships: 15 } },
    canSync: true, syncing: false });
  receive(groupedMessage());
  assert.equal(element('analysis-badge').textContent, 'Analysis: Complete');
  assert.equal(element('sync-badge').textContent, 'AI Context: Synchronized');
  assert.equal(element('conformance-badge').textContent, 'Conformance: 1 violations');
});
test('generated interpretation uses readable fields and an explicit review badge', () => {
  const { element, receive } = view();
  receive({ type: 'proposal', response, canApprove: true });
  assert.equal(element('interpretation-card').hidden, false);
  assert.equal(element('rule-badge').textContent, 'Ready for review');
  const values = element('interpretation').children.map(child => child.textContent);
  assert.ok(values.includes('PaymentGateway (COMPONENT)') && values.includes('PROJECT'));
  assert.ok(!values.some(value => value.includes('{"entity_type"')));
});
test('conflict cards preserve safe text and their confirmation action reuses host approval', () => {
  const { element, receive, sent } = view();
  receive({ type: 'proposal', response, canApprove: true });
  receive({ type: 'conflicts', conflicts: { conflicts: [{ existing_rule_id: 'CUSTOM_001', reason: '<script>unsafe</script>' }] } });
  assert.equal(element('conflict-card').hidden, false);
  assert.equal(element('rule-badge').textContent, 'Conflict detected');
  assert.equal(element('conflicts').children[0].children[1].textContent, '<script>unsafe</script>');
  element('confirm-approval').fire('click');
  assert.deepEqual(sent, [{ type: 'approve' }]);
});
test('conflict card cancellation never sends an approval or override request', () => {
  const { element, receive, sent } = view();
  receive({ type: 'proposal', response, canApprove: true });
  receive({ type: 'conflicts', conflicts: { conflicts: [{ existing_rule_id: 'CUSTOM_001', reason: 'Restriction' }] } });
  element('cancel-conflict').fire('click');
  assert.equal(element('conflict-card').hidden, true);
  assert.match(element('rule-status').textContent, /has not been approved/);
  assert.deepEqual(sent, []);
});
test('the file link on a violation card uses existing ID-based navigation', () => {
  const { element, receive, sent } = view();
  receive(groupedMessage());
  const link = element('violation-list').children[0].children[2];
  assert.ok(link.textContent.includes('src/Example.java:1'));
  link.fire('click');
  assert.deepEqual(sent, [{ type: 'openViolation', violationId: exampleViolation.violation_id }]);
});
test('backend configuration display uses supplied host information without polling', () => {
  const { element, receive, sent } = view();
  receive({ type: 'backendStatus', configured: true, host: 'gpu.example' });
  assert.equal(element('backend-status').textContent, 'AI Backend: Configured · gpu.example');
  receive({ type: 'backendStatus', configured: false });
  assert.equal(element('backend-status').textContent, 'AI Backend: Configuration required');
  assert.deepEqual(sent, []);
});
test('approval and error states have distinct text badges and preserve error details', () => {
  const { element, receive } = view();
  receive({ type: 'approved', approval: { duplicate: false, rule_id: 'CUSTOM_001' } });
  assert.equal(element('rule-badge').textContent, 'Approved');
  receive({ type: 'approved', approval: { duplicate: true, rule_id: 'CUSTOM_001' } });
  assert.equal(element('rule-badge').textContent, 'Duplicate rule');
  receive({ type: 'error', message: 'Backend unavailable.', canApprove: false, errors: [{ path: 'rule', message: 'Invalid rule' }] });
  assert.equal(element('rule-badge').textContent, 'Request failed');
  assert.equal(element('validation-errors').hidden, false);
  assert.equal(element('rule-status').textContent, 'Backend unavailable.');
});
test('styling supports narrow layouts and uses theme variables rather than fixed bright colors', () => {
  assert.ok(architectureStyles.includes('@media (max-width: 440px)'));
  assert.ok(architectureStyles.includes('--vscode-input-background') && architectureStyles.includes('--vscode-foreground'));
  assert.ok(architectureStyles.includes(':focus-visible') && architectureStyles.includes('[hidden]'));
});
