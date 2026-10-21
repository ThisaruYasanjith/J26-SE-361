import * as assert from 'node:assert/strict';
import { test } from 'node:test';
import { ArchitectureBackendClient, BackendApiError, normalizeBaseUrl } from '../../architecture/backendClient';
import { GeneratedRuleResponse, ProjectContext, ValidRuleEnvelope } from '../../architecture/contracts';
import { conformanceResponse, exampleViolation } from './conformanceFixtures';

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
    calls.push({ url: String(url), body: options?.body === undefined ? undefined : JSON.parse(String(options.body)) });
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

const projectContext: ProjectContext = {
  schema_version: '1.0', project_name: 'payments', project_root: '.', components: [], relationships: [],
};
const syncResult = { updated: true, project_name: 'payments', components: 0, relationships: 0, rag_invalidated: true };

test('sync uses PUT, configured URL and the complete context without a wrapper', async () => {
  const logs: string[] = [];
  let configured = 'https://first.example/api/';
  const urls: string[] = [];
  const client = new ArchitectureBackendClient(() => configured, { appendLine: line => logs.push(line) }, async (url, options) => {
    urls.push(String(url));
    assert.equal(options?.method, 'PUT');
    assert.deepEqual(JSON.parse(String(options?.body)), projectContext);
    return new Response(JSON.stringify(syncResult));
  });
  assert.deepEqual(await client.syncProjectContext(projectContext), syncResult);
  configured = 'http://127.0.0.1:9000/prefix';
  await client.syncProjectContext(projectContext);
  assert.deepEqual(urls, ['https://first.example/api/context/project', 'http://127.0.0.1:9000/prefix/context/project']);
  for (const text of ['payments', 'HTTP 200', '0 components', '0 relationships', 'RAG index invalidated']) {
    assert.ok(logs.some(line => line.includes(text)));
  }
  assert.ok(!logs.some(line => line.includes('schema_version')));
});

test('sync exposes FastAPI validation field paths without logging the entire rejected body', async () => {
  const { client, logs } = setup({ detail: [{ loc: ['body', 'components', 0, 'name'], msg: 'Field required', input: 'private data' }] }, 422);
  await assert.rejects(client.syncProjectContext(projectContext), (error: unknown) => error instanceof BackendApiError
    && error.status === 422 && error.validationErrors[0].path === 'body.components.0.name');
  assert.ok(logs.some(line => line.includes('body.components.0.name')));
  assert.ok(!logs.some(line => line.includes('private data')));
});

for (const status of [400, 503]) {
  test(`sync handles HTTP ${status}`, async () => {
    await assert.rejects(setup({ detail: 'Cannot store context' }, status).client.syncProjectContext(projectContext),
      (error: unknown) => error instanceof BackendApiError && error.status === status);
  });
}

test('sync handles an unavailable backend', async () => {
  const client = new ArchitectureBackendClient(() => 'https://gpu.example', { appendLine() {} }, async () => { throw new TypeError('fetch failed'); });
  await assert.rejects(client.syncProjectContext(projectContext), (error: unknown) => error instanceof BackendApiError && error.kind === 'network');
});

test('sync handles timeout using the existing request cancellation', async () => {
  const client = new ArchitectureBackendClient(() => 'https://gpu.example', { appendLine() {} }, async (_url, options) => new Promise<Response>((_resolve, reject) => {
    options?.signal?.addEventListener('abort', () => reject(new Error('Aborted')), { once: true });
  }), 10);
  await assert.rejects(client.syncProjectContext(projectContext), (error: unknown) => error instanceof BackendApiError && error.kind === 'timeout');
});

for (const data of [{ ...syncResult, updated: false }, { ...syncResult, components: -1 }, { ...syncResult, rag_invalidated: false }]) {
  test('sync rejects an unexpected response contract', async () => {
    await assert.rejects(setup(data).client.syncProjectContext(projectContext),
      (error: unknown) => error instanceof BackendApiError && error.kind === 'invalid-response');
  });
}

test('conformance uses only its deterministic POST endpoint with the configured URL prefix', async () => {
  let configured = 'https://first.example/api/';
  const urls: string[] = [];
  const logs: string[] = [];
  const response = conformanceResponse();
  const client = new ArchitectureBackendClient(() => configured, { appendLine: line => logs.push(line) }, async (url, options) => {
    urls.push(String(url));
    assert.equal(options?.method, 'POST');
    assert.equal(options?.body, undefined);
    return new Response(JSON.stringify(response));
  });
  assert.deepEqual(await client.checkConformance(), response);
  configured = 'http://localhost:9000/other';
  await client.checkConformance();
  assert.deepEqual(urls, ['https://first.example/api/conformance/check', 'http://localhost:9000/other/conformance/check']);
  assert.ok(logs.some(line => line.includes('HTTP 200')) && logs.some(line => line.includes('1 violations')));
});
test('conformance accepts an empty conformant result', async () => {
  const response = conformanceResponse([]);
  assert.deepEqual(await setup(response).client.checkConformance(), response);
});
for (const status of [400, 409, 422, 500, 503]) {
  test(`conformance reports HTTP ${status}`, async () => {
    await assert.rejects(setup({ detail: 'Analyze and sync a project first.' }, status).client.checkConformance(),
      (error: unknown) => error instanceof BackendApiError && error.status === status);
  });
}
for (const response of [{}, { ...conformanceResponse(), conformant: true }, { ...conformanceResponse(), rule_metadata: {} },
  { ...conformanceResponse(), summary: { total: 2, base_rule_violations: 2, custom_rule_violations: 0 } },
  conformanceResponse([{ ...exampleViolation, severity: 'HINT' as never }]),
  conformanceResponse([{ ...exampleViolation, message: '' }]), conformanceResponse([exampleViolation, exampleViolation])]) {
  test('malformed or inconsistent conformance response is rejected', async () => {
    await assert.rejects(setup(response).client.checkConformance(),
      (error: unknown) => error instanceof BackendApiError && error.kind === 'invalid-response');
  });
}
test('conformance preserves findings with absent evidence for panel-only display', async () => {
  const response = conformanceResponse([{ ...exampleViolation, file_path: undefined, start_line: undefined, end_line: undefined }]);
  const result = await setup(response).client.checkConformance();
  assert.equal(result.violations.length, 1);
  assert.equal(result.violations[0].file_path, undefined);
});
test('malformed evidence types do not hide otherwise valid conformance findings', async () => {
  const response = { ...conformanceResponse(), violations: [{ ...exampleViolation, start_line: 'bad', end_line: {} }] };
  const result = await setup(response).client.checkConformance();
  assert.equal(result.violations[0].message, exampleViolation.message);
  assert.equal(result.violations[0].start_line, undefined);
  assert.equal(result.violations[0].end_line, undefined);
  assert.equal(result.summary.total, 1);
});
test('a malformed source path becomes unavailable without changing the violation', async () => {
  const response = { ...conformanceResponse(), violations: [{ ...exampleViolation, file_path: { unexpected: 'object' } }] };
  const result = await setup(response).client.checkConformance();
  assert.equal(result.violations[0].file_path, undefined);
  assert.equal(result.violations[0].violation_id, exampleViolation.violation_id);
});
test('conformance reports malformed response JSON', async () => {
  const client = new ArchitectureBackendClient(() => 'https://backend.example', { appendLine() {} }, async () => new Response('<html>not JSON</html>'));
  await assert.rejects(client.checkConformance(), (error: unknown) => error instanceof BackendApiError && error.kind === 'invalid-response');
});
test('conformance reports network failure', async () => {
  const client = new ArchitectureBackendClient(() => 'https://backend.example', { appendLine() {} }, async () => { throw new Error('Network failure'); });
  await assert.rejects(client.checkConformance(), (error: unknown) => error instanceof BackendApiError && error.kind === 'network');
});
test('conformance timeout uses the shared HTTP cancellation', async () => {
  const client = new ArchitectureBackendClient(() => 'https://backend.example', { appendLine() {} }, async (_url, options) => new Promise<Response>((_resolve, reject) => {
    options?.signal?.addEventListener('abort', () => reject(new Error('Aborted')), { once: true });
  }), 10);
  await assert.rejects(client.checkConformance(), (error: unknown) => error instanceof BackendApiError && error.kind === 'timeout');
});
test('conformance accepts external cancellation without disposing the shared backend client', async () => {
  const cancellation = new AbortController();
  let calls = 0;
  const client = new ArchitectureBackendClient(() => 'https://backend.example', { appendLine() {} }, async (_url, options) => {
    calls++;
    if (calls > 1) { return new Response(JSON.stringify(conformanceResponse([]))); }
    return new Promise<Response>((_resolve, reject) => options?.signal?.addEventListener('abort', () => reject(new Error('Aborted')), { once: true }));
  });
  const pending = client.checkConformance(cancellation.signal);
  cancellation.abort();
  await assert.rejects(pending, (error: unknown) => error instanceof BackendApiError && error.kind === 'cancelled');
  assert.ok((await client.checkConformance()).conformant);
});
