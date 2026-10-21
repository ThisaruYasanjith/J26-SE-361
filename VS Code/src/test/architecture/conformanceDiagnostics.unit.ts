import * as assert from 'node:assert/strict';
import { test } from 'node:test';
import * as fs from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { createRequire } from 'node:module';
import { runInNewContext } from 'node:vm';
import { exampleViolation } from './conformanceFixtures';

class MockRange {
  constructor(readonly startLine: number, readonly startCharacter: number, readonly endLine: number, readonly endCharacter: number) {}
}
class MockDiagnostic {
  source?: string;
  code?: string;
  constructor(readonly range: MockRange, readonly message: string, readonly severity: number) {}
}
function adapter() {
  let clears = 0;
  let disposed = false;
  let groups: [{ fsPath: string }, MockDiagnostic[]][] = [];
  const opened: string[] = [];
  const revealed: MockRange[] = [];
  const api = {
    languages: { createDiagnosticCollection: (name: string) => {
      assert.equal(name, 'architectureGovernance');
      return { clear: () => { clears++; groups = []; }, set: (entries: typeof groups) => { groups = entries; }, dispose: () => { disposed = true; } };
    } },
    Range: MockRange, Diagnostic: MockDiagnostic, Uri: { file: (fsPath: string) => ({ fsPath }) },
    workspace: { openTextDocument: async (uri: { fsPath: string }) => {
      opened.push(uri.fsPath); return { validateRange: (range: MockRange) => range };
    } },
    window: { showTextDocument: async (_document: unknown, options: { selection: MockRange }) => ({
      revealRange: (range: MockRange) => { assert.equal(range, options.selection); revealed.push(range); },
    }) },
    TextEditorRevealType: { InCenter: 1 },
  };
  const file = path.resolve(__dirname, '../../architecture/conformanceDiagnostics.js');
  const actualRequire = createRequire(file);
  const exports = {} as typeof import('../../architecture/conformanceDiagnostics');
  runInNewContext(readFileSync(file, 'utf8'), { exports, require: (name: string) => name === 'vscode' ? api : actualRequire(name) });
  const diagnostics = new exports.VscodeConformanceDiagnostics({ appendLine() {} });
  return { diagnostics, opened, revealed, groups: () => groups, clears: () => clears, disposed: () => disposed };
}

test('VS Code adapter publishes grouped Problems diagnostics with source, rule code, severity and range', async () => {
  const { diagnostics, groups, clears, disposed } = adapter();
  const entry = { violationId: 'V', filePath: path.resolve('Example.java'), range: {
    startLine: 0, startCharacter: 0, endLine: 1, endCharacter: 4,
  }, message: exampleViolation.message, code: exampleViolation.rule_id, source: 'Architecture Governance' as const, severity: 0 };
  diagnostics.replace([entry, { ...entry, violationId: 'V2', severity: 1 }]);
  assert.equal(groups().length, 1);
  const [uri, items] = groups()[0];
  assert.equal(uri.fsPath, entry.filePath);
  assert.equal(items.length, 2);
  assert.equal(items[0].message, exampleViolation.message);
  assert.equal(items[0].source, 'Architecture Governance');
  assert.equal(items[0].code, exampleViolation.rule_id);
  assert.equal(items[0].range.startLine, 0);
  assert.equal(items[1].severity, 1);
  diagnostics.replace([]);
  assert.equal(groups().length, 0);
  assert.ok(clears() >= 2);
  diagnostics.dispose();
  diagnostics.clear();
  assert.ok(disposed());
});
test('navigation opens the canonical file and reveals its converted range; unsafe paths never open', async t => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'architecture-open-'));
  t.after(async () => {
    assert.equal(path.dirname(root), path.resolve(os.tmpdir()));
    await fs.rm(root, { recursive: true, force: true });
  });
  await fs.mkdir(path.join(root, 'src'));
  await fs.writeFile(path.join(root, 'src', 'Example.java'), 'class Example {}');
  const { diagnostics, opened, revealed } = adapter();
  assert.equal(await diagnostics.open(root, exampleViolation), true);
  assert.deepEqual(opened, [await fs.realpath(path.join(root, 'src', 'Example.java'))]);
  assert.equal(revealed[0].startLine, 0);
  assert.equal(await diagnostics.open(root, { ...exampleViolation, file_path: '../../outside.java' }), false);
  await fs.unlink(path.join(root, 'src', 'Example.java'));
  assert.equal(await diagnostics.open(root, exampleViolation), false);
  assert.equal(opened.length, 1);
  diagnostics.dispose();
});
