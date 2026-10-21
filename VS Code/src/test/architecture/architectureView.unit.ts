import * as assert from 'node:assert/strict';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';
import { ruleWebviewScript } from '../../architecture/architectureView';

class Element {
  textContent = '';
  disabled = false;
  hidden = false;
  value = '';
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
  assert.equal(element('conflicts').textContent, 'CUSTOM_001: ONLY restriction');
  assert.match(element('rule-status').textContent, /has not been approved/);
  assert.equal(element('approve').disabled, false);
});
test('duplicate approval gives a clear success message and disables saving', () => {
  const { element, receive } = view();
  receive({ type: 'approved', approval: { duplicate: true, rule_id: 'CUSTOM_001' } });
  assert.match(element('rule-status').textContent, /Already approved as CUSTOM_001/);
  assert.equal(element('approve').disabled, true);
});
