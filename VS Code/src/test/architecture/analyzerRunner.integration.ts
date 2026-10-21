import * as assert from 'node:assert/strict';
import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import { tmpdir } from 'node:os';
import { test } from 'node:test';
import { AnalyzerRunner } from '../../architecture/analyzerRunner';

test('runs the real Java analyzer on an isolated copy of a demo project', {
  skip: process.env.RUN_ANALYZER_INTEGRATION !== '1',
}, async t => {
  const demo = process.env.ANALYZER_DEMO_PROJECT;
  if (!demo) { t.skip('Set ANALYZER_DEMO_PROJECT to a Java demo project root.'); return; }
  const temporary = await fs.mkdtemp(path.join(tmpdir(), 'j26-analyzer-integration-'));
  t.after(async () => {
    assert.equal(path.dirname(temporary), path.resolve(tmpdir()));
    await fs.rm(temporary, { recursive: true, force: true });
  });
  const project = path.join(temporary, 'architecture demo project');
  await fs.cp(path.join(demo, 'src'), path.join(project, 'src'), { recursive: true });
  const runner = new AnalyzerRunner(path.resolve(__dirname, '../../..'), { appendLine: line => console.log(line) });
  const result = await runner.analyze({ name: 'demo', fsPath: project, scheme: 'file' });
  assert.equal(result.projectName, 'architecture demo project');
  assert.ok(result.componentCount > 0);
  const generated = JSON.parse(await fs.readFile(result.contextPath, 'utf8'));
  assert.equal(generated.components.length, result.componentCount);
  assert.equal(generated.relationships.length, result.relationshipCount);
  console.log('Real analyzer summary:', JSON.stringify(result));
});
