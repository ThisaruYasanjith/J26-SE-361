import * as assert from 'node:assert/strict';
import { test } from 'node:test';
import { ArchitectureBackend, BackendApiError } from '../../architecture/backendClient';
import { ApprovalResponse, ConflictResponse, GeneratedRuleResponse } from '../../architecture/contracts';
import { ArchitectureRuleWorkflow } from '../../architecture/ruleWorkflow';

// Fixtures stay local so loading this suite does not register another suite's tests.
const rule = { status: 'VALID', reason_code: null, rule: {
  rule_type: 'COMPONENT_ACCESS', source: { entity_type: 'COMPONENT', name: 'PaymentService' }, relationship: 'DEPENDS_ON',
  target: { entity_type: 'COMPONENT', name: 'PaymentGateway' }, action: 'ONLY', scope: { type: 'PROJECT', value: null }, is_exception: false,
} };
const generation: GeneratedRuleResponse = { generated_text: JSON.stringify(rule), json_valid: true, schema_valid: true, validation_errors: [], rule, retrieved_context: [] };
const conflict: ConflictResponse = { has_conflict: true, duplicate: false, conflicts: [{ existing_rule_id: 'CUSTOM_001', reason: 'ONLY restriction' }] };
const approval: ApprovalResponse = { approved: true, rule_id: 'CUSTOM_002', conflicts_confirmed: false, duplicate: false };
function setup(response = generation, checks: ConflictResponse = { has_conflict: false, duplicate: false, conflicts: [] }) {
  const calls: boolean[] = [];
  let checked = 0;
  const backend: ArchitectureBackend = {
    baseUrl: 'https://gpu.example',
    async generateRule() { return response; },
    async checkConflicts() { checked++; return checks; },
    async approveRule(_rule, confirmed = false) { calls.push(confirmed); return { ...approval, conflicts_confirmed: confirmed }; },
  };
  return { backend, workflow: new ArchitectureRuleWorkflow(backend), calls, checked: () => checked };
}
test('generation shows a proposal and never auto-approves it', async () => {
  const { workflow, calls, checked } = setup();
  assert.deepEqual(await workflow.generate(' Only PaymentService may depend on PaymentGateway. '), generation);
  assert.ok(workflow.canApprove);
  assert.equal(checked(), 0);
  assert.deepEqual(calls, []);
});
for (const response of [
  { ...generation, rule: { status: 'AMBIGUOUS', rule: null, reason_code: 'MISSING_TARGET' } },
  { ...generation, rule: { status: 'UNSUPPORTED', rule: null, reason_code: 'NOT_ARCHITECTURAL_CONSTRAINT' } },
  { ...generation, schema_valid: false }, { ...generation, json_valid: false, schema_valid: false, rule: null },
]) {
  test('uncertain or invalid interpretations cannot be approved', async () => {
    const { workflow, calls } = setup(response);
    await workflow.generate('Explain access.');
    assert.equal(workflow.canApprove, false);
    await assert.rejects(workflow.approve(async () => true), BackendApiError);
    assert.deepEqual(calls, []);
  });
}
test('approval without conflicts sends false and disables further approval', async () => {
  const { workflow, calls } = setup();
  await workflow.generate('Explain access.');
  const result = await workflow.approve(async () => { throw new Error('Unexpected confirmation'); });
  assert.deepEqual(result, { cancelled: false, approval });
  assert.deepEqual(calls, [false]);
  assert.equal(workflow.canApprove, false);
  await workflow.approve(async () => true);
  assert.deepEqual(calls, [false]);
});
test('cancelling a conflict never sends approval', async () => {
  const { workflow, calls } = setup(generation, conflict);
  await workflow.generate('Explain access.');
  assert.deepEqual(await workflow.approve(async shown => { assert.deepEqual(shown, conflict); return false; }), { cancelled: true });
  assert.deepEqual(calls, []);
  assert.ok(workflow.canApprove);
});
test('only explicit confirmation sends the override flag', async () => {
  const { workflow, calls } = setup(generation, conflict);
  await workflow.generate('Explain access.');
  const result = await workflow.approve(async () => true);
  assert.deepEqual(calls, [true]);
  assert.ok(!result.cancelled && result.approval.conflicts_confirmed);
});
for (const confirmed of [false, true]) {
  test(`a late HTTP 409 requires confirmation (choice=${confirmed})`, async () => {
    const { backend, workflow, calls } = setup();
    backend.approveRule = async (_rule, flag = false) => {
      calls.push(flag);
      if (!flag) { throw new BackendApiError('http', 'Conflict', 409, conflict); }
      return { ...approval, conflicts_confirmed: true };
    };
    await workflow.generate('Explain access.');
    const result = await workflow.approve(async () => confirmed);
    assert.equal(result.cancelled, !confirmed);
    assert.deepEqual(calls, confirmed ? [false, true] : [false]);
  });
}
test('duplicate approval is handled without an unnecessary override', async () => {
  const { backend, workflow, calls } = setup(generation, { ...conflict, duplicate: true });
  backend.approveRule = async (_rule, flag = false) => { calls.push(flag); return { ...approval, duplicate: true }; };
  await workflow.generate('Explain access.');
  const result = await workflow.approve(async () => { throw new Error('Unexpected confirmation'); });
  assert.ok(!result.cancelled && result.approval.duplicate);
  assert.deepEqual(calls, [false]);
});
test('a changed backend URL invalidates the proposal', async () => {
  const { backend, workflow, calls } = setup();
  await workflow.generate('Explain access.');
  Object.defineProperty(backend, 'baseUrl', { value: 'https://another.example' });
  await assert.rejects(workflow.approve(async () => true), (error: unknown) => error instanceof BackendApiError && error.kind === 'configuration');
  assert.deepEqual(calls, []);
  assert.equal(workflow.canApprove, false);
});
test('changing backend settings in the confirmation dialog prevents persistence', async () => {
  const { backend, workflow, calls } = setup(generation, conflict);
  await workflow.generate('Explain access.');
  await assert.rejects(workflow.approve(async () => {
    Object.defineProperty(backend, 'baseUrl', { value: 'https://another.example' });
    return true;
  }), BackendApiError);
  assert.deepEqual(calls, []);
});
test('editing clears a proposal and prevents stale approval', async () => {
  const { workflow, calls } = setup();
  await workflow.generate('Explain access.');
  workflow.clear();
  await assert.rejects(workflow.approve(async () => true), BackendApiError);
  assert.deepEqual(calls, []);
});
test('failed generation clears the previous approvable proposal', async () => {
  const { backend, workflow } = setup();
  await workflow.generate('Explain access.');
  backend.generateRule = async () => { throw new BackendApiError('network', 'Unavailable'); };
  await assert.rejects(workflow.generate('New requirement.'), BackendApiError);
  assert.equal(workflow.canApprove, false);
});
