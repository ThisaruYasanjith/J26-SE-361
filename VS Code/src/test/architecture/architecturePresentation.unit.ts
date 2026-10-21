import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import * as path from 'node:path';
import { test } from 'node:test';
import type * as vscode from 'vscode';
import { ApprovedRuleViewCache, architectureUiMode, violationSummary } from '../../architecture/architecturePresentation';
import { ArchitectureViolation, ValidRuleEnvelope } from '../../architecture/contracts';
import { conformanceResponse, exampleViolation } from './conformanceFixtures';

test('product mode is the configured default and developer mode remains available', () => {
  const manifest = JSON.parse(readFileSync(path.resolve(__dirname, '../../..', 'package.json'), 'utf8'));
  const setting = manifest.contributes.configuration.properties['architectureGovernance.uiMode'];
  assert.equal(setting.default, 'product');
  assert.deepEqual(setting.enum, ['product', 'developer']);
  assert.equal(architectureUiMode(undefined), 'product');
  assert.equal(architectureUiMode('invalid'), 'product');
  assert.equal(architectureUiMode('developer'), 'developer');
  assert.ok(manifest.contributes.commands.some((item: { command: string }) => item.command === 'architectureGovernance.switchUiMode'));
});

test('display categories partition dependency and structural evidence without mutating results', () => {
  const relationships = ['DEPENDS_ON', 'CALLS', 'IMPORTS', 'LOCATED_IN', 'EXTENDS', 'IMPLEMENTS', 'CONTAINS'] as const;
  const findings: ArchitectureViolation[] = relationships.map((relationship, i) => ({ ...exampleViolation, relationship, violation_id: String(i), rule_id: String(i) }));
  findings.push({ ...exampleViolation, violation_id: 'missing-evidence', rule_id: 'placement', relationship: null });
  const result = conformanceResponse(findings); result.rule_metadata.placement.rule_type = 'PACKAGE_PLACEMENT';
  const before = JSON.stringify(result);
  assert.deepEqual(violationSummary(result), { total: 8, dependency: 3, structure: 5 });
  assert.equal(JSON.stringify(result), before);
});

test('confirmed-rule display cache survives reopening, scopes entries and deduplicates IDs', async () => {
  const values = new Map<string, unknown>();
  const storage = { get: (key: string) => values.get(key), update: async (key: string, value: unknown) => { values.set(key, value); } } as unknown as vscode.Memento;
  const rule: ValidRuleEnvelope = { status: 'VALID', reason_code: null, rule: {
    rule_type: 'COMPONENT_ACCESS', source: { entity_type: 'COMPONENT', name: 'PaymentService' }, relationship: 'DEPENDS_ON',
    target: { entity_type: 'COMPONENT', name: 'PaymentGateway' }, action: 'ONLY', scope: { type: 'PROJECT', value: null }, is_exception: false,
  } };
  const cache = new ApprovedRuleViewCache(storage);
  assert.deepEqual(cache.read('project-a/backend-a'), []);
  await cache.record('project-a/backend-a', rule, 'CUSTOM_001');
  await cache.record('project-a/backend-a', rule, 'CUSTOM_001');
  const reopened = new ApprovedRuleViewCache(storage);
  assert.equal(reopened.read('project-a/backend-a').length, 1);
  assert.equal(reopened.read('project-a/backend-a')[0].rule_id, 'CUSTOM_001');
  assert.deepEqual(reopened.read('project-b/backend-a'), []);
  assert.deepEqual(reopened.read('project-a/backend-b'), []);
});
