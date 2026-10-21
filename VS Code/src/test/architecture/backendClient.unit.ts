import * as assert from 'node:assert/strict';
import { test } from 'node:test';
import { ArchitectureBackendClient, BackendApiError, normalizeBaseUrl } from '../../architecture/backendClient';
import { GeneratedRuleResponse, ValidRuleEnvelope } from '../../architecture/contracts';

export const rule: ValidRuleEnvelope = {
  status: 'VALID', reason_code: null,
  rule: {
    rule_type: 'COMPONENT_ACCESS', source: { entity_type: 'COMPONENT', name: 'PaymentService' },
    relationship: 'DEPENDS_ON', target: { entity_type: 'COMPONENT', name: 'PaymentGateway' }, action: 'ONLY',
    scope: { type: 'PROJECT', value: null }, is_exception: false,
  },
};
export const generation: GeneratedRuleResponse = {
  generated_text: JSON.stringify(rule), json_valid: true, schema_valid: true, validation_errors: [], rule, retrieved_context: [],
};
export const conflict = { has_conflict: true, duplicate: false, conflicts: [{ existing_rule_id: 'CUSTOM_001', reason: 'Existing ONLY restriction.' }] };
export const approval = { approved: true, rule_id: 'CUSTOM_002', conflicts_confirmed: false, duplicate: false };

function setup(data: unknown, status = 200) {
  const calls: { url: string; body: unknown }[] = [];
  const logs: string[] = [];
  const fetcher: typeof fetch = async (url, options) => {
    calls.push({ url: String(url), body: JSON.parse(String(options?.body)) });
    return new Response(JSON.stringify(data), { status });
  };
  const client = new ArchitectureBackendClient(() => 'https://gpu.example/api/', { appendLine: line => logs.push(line) }, fetcher);
  return { client, calls, logs };
}

for (const [input, expected] of [
  [' http://127.0.0.1:8000/// ', 'http://127.0.0.1:8000'],
  ['https://gpu.example/prefix///', 'https://gpu.example/prefix'], ['https://gpu.example', 'https://gpu.example'],
]) {
  test(`normalizes URL ${input}`, () => { assert.equal(normalizeBaseUrl(input), expected); });
}
for (const input of ['', 'not a URL', 'file:///tmp/backend', 'https://user:secret@gpu.example', 'https://gpu.example?token=secret', 'https://gpu.example/#fragment']) {
  test('rejects invalid or credential-bearing base URL', () => { assert.throws(() => normalizeBaseUrl(input), BackendApiError); });
}
test('generates using trimmed input, configured prefix and actual backend payload', async () => {
  const { client, calls, logs } = setup(generation);
  assert.deepEqual(await client.generateRule('  Only PaymentService may depend on PaymentGateway. '), generation);
  assert.deepEqual(calls, [{ url: 'https://gpu.example/api/rules/generate', body: { requirement: 'Only PaymentService may depend on PaymentGateway.', use_rag: true } }]);
  assert.ok(logs.some(line => line.includes('HTTP 200')));
  assert.ok(!logs.some(line => line.includes('Only PaymentService may')));
});
for (const status of ['AMBIGUOUS', 'UNSUPPORTED']) {
  test(`accepts ${status} response`, async () => {
    const response = { ...generation, rule: { status, rule: null, reason_code: 'MISSING_TARGET' } };
    assert.deepEqual(await setup(response).client.generateRule('Explain access.'), response);
  });
}
test('preserves parseable but schema-invalid output for display', async () => {
  const response = { ...generation, schema_valid: false, rule: { action: 'WRONG' }, validation_errors: [{ path: 'rule.action', message: 'Unsupported action' }] };
  const { client, logs } = setup(response);
  assert.deepEqual(await client.generateRule('Explain access.'), response);
  assert.ok(logs.some(line => line.includes('rule.action')));
});
test('preserves invalid JSON response without treating it as a transport failure', async () => {
  const response = { ...generation, json_valid: false, schema_valid: false, rule: null, generated_text: 'invalid', validation_errors: [{ path: '$', message: 'Not JSON' }] };
  assert.deepEqual(await setup(response).client.generateRule('Explain access.'), response);
});
test('rejects blank input before making an HTTP request', () => {
  const { client, calls } = setup(generation);
  assert.throws(() => client.generateRule(' \n '), BackendApiError);
  assert.equal(calls.length, 0);
});
for (const data of [{}, { ...generation, schema_valid: true, rule: null }, { ...generation, retrieved_context: [{ score: 'wrong' }] }]) {
  test('rejects an unexpected backend contract', async () => {
    await assert.rejects(setup(data).client.generateRule('Explain access.'), (error: unknown) => error instanceof BackendApiError && error.kind === 'invalid-response');
  });
}
test('reports non-JSON HTTP success clearly', async () => {
  const fetcher: typeof fetch = async () => new Response('<html>wrong backend</html>');
  const client = new ArchitectureBackendClient(() => 'https://gpu.example', { appendLine() {} }, fetcher);
  await assert.rejects(client.generateRule('Explain access.'), (error: unknown) => error instanceof BackendApiError && error.kind === 'invalid-response');
});
for (const status of [400, 422, 503]) {
  test(`reports backend HTTP ${status}`, async () => {
    await assert.rejects(setup({ detail: 'Request could not be processed', validation_errors: [{ path: 'rule', message: 'Invalid rule' }] }, status).client.generateRule('Explain access.'),
      (error: unknown) => error instanceof BackendApiError && error.kind === 'http' && error.status === status && error.validationErrors.length === 1);
  });
}
test('retains structured conflict details from HTTP 409', async () => {
  await assert.rejects(setup({ detail: 'Conflicting rule', ...conflict }, 409).client.approveRule(rule),
    (error: unknown) => error instanceof BackendApiError && error.status === 409 && error.conflicts?.conflicts[0].existing_rule_id === 'CUSTOM_001');
});
test('checks conflicts with the full rule envelope', async () => {
  const { client, calls } = setup(conflict);
  assert.deepEqual(await client.checkConflicts(rule), conflict);
  assert.deepEqual(calls[0], { url: 'https://gpu.example/api/rules/check-conflicts', body: { rule } });
});
test('approves with explicit confirmation only when supplied', async () => {
  const { client, calls } = setup(approval);
  assert.deepEqual(await client.approveRule(rule), approval);
  await client.approveRule(rule, true);
  assert.deepEqual(calls.map(call => call.body), [{ rule, confirm_conflicts: false }, { rule, confirm_conflicts: true }]);
});
test('recognizes duplicate approval', async () => {
  const response = { ...approval, duplicate: true };
  assert.deepEqual(await setup(response).client.approveRule(rule), response);
});
test('rereads the configured URL for each request', async () => {
  let configured = 'https://first.example';
  const urls: string[] = [];
  const client = new ArchitectureBackendClient(() => configured, { appendLine() {} }, async url => { urls.push(String(url)); return new Response(JSON.stringify(generation)); });
  await client.generateRule('Explain access.');
  configured = 'https://second.example/prefix';
  await client.generateRule('Explain access.');
  assert.deepEqual(urls, ['https://first.example/rules/generate', 'https://second.example/prefix/rules/generate']);
});
test('reports an unavailable backend without a raw stack trace', async () => {
  const client = new ArchitectureBackendClient(() => 'https://gpu.example', { appendLine() {} }, async () => { throw new TypeError('fetch failed'); });
  await assert.rejects(client.generateRule('Explain access.'), (error: unknown) => error instanceof BackendApiError && error.kind === 'network' && !error.message.includes('TypeError'));
});
test('aborts a timed-out request', async () => {
  const fetcher: typeof fetch = async (_url, options) => new Promise<Response>((_resolve, reject) => {
    options?.signal?.addEventListener('abort', () => reject(new Error('Aborted')), { once: true });
  });
  const client = new ArchitectureBackendClient(() => 'https://gpu.example', { appendLine() {} }, fetcher, 10);
  await assert.rejects(client.generateRule('Explain access.'), (error: unknown) => error instanceof BackendApiError && error.kind === 'timeout');
});
