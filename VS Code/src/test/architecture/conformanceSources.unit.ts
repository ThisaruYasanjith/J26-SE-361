import * as assert from 'node:assert/strict';
import { test, TestContext } from 'node:test';
import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { ConformanceSourceMapper, diagnosticRange, diagnosticSeverity } from '../../architecture/conformanceSources';
import { exampleViolation } from './conformanceFixtures';

async function project(t: TestContext) {
  const temporary = await fs.mkdtemp(path.join(os.tmpdir(), 'architecture-source-'));
  t.after(async () => {
    assert.equal(path.dirname(temporary), path.resolve(os.tmpdir()));
    await fs.rm(temporary, { recursive: true, force: true });
  });
  const root = path.join(temporary, 'project with spaces');
  await fs.mkdir(path.join(root, 'src'), { recursive: true });
  await fs.writeFile(path.join(root, 'src', 'Example.java'), 'class Example {\r\n  void run() {}\r\n}');
  const logs: string[] = [];
  return { root, temporary, logs, mapper: new ConformanceSourceMapper({ appendLine: line => logs.push(line) }) };
}

for (const [severity, expected] of [['ERROR', 0], ['WARNING', 1], ['INFO', 2]] as const) {
  test(`${severity} maps to VS Code severity ${expected}`, () => assert.equal(diagnosticSeverity(severity), expected));
}
test('line one is converted to zero with a whole-line UTF-16 range', () => {
  assert.deepEqual(diagnosticRange({ start_line: 1, end_line: 1 }, ['x😀']), {
    startLine: 0, startCharacter: 0, endLine: 0, endCharacter: 3,
  });
  assert.deepEqual(diagnosticRange({ start_line: 2 }, ['first', 'second']), {
    startLine: 1, startCharacter: 0, endLine: 1, endCharacter: 6,
  });
});
test('range end is bounded to the actual document', () => {
  assert.deepEqual(diagnosticRange({ start_line: 1, end_line: 100 }, ['first', 'last']), {
    startLine: 0, startCharacter: 0, endLine: 1, endCharacter: 4,
  });
});
for (const location of [{}, { start_line: null }, { start_line: 0 }, { start_line: -2 }, { start_line: 1.5 },
  { start_line: NaN }, { start_line: 10 }, { start_line: 2, end_line: 1 }]) {
  test('missing or invalid locations have no diagnostic range', () => {
    assert.equal(diagnosticRange(location, ['one', 'two']), undefined);
  });
}
test('source paths and messages are mapped without adding backend metadata to messages', async t => {
  const { mapper, root } = await project(t);
  const entries = await mapper.prepare(root, [exampleViolation]);
  assert.equal(entries.length, 1);
  assert.equal(entries[0].filePath, await fs.realpath(path.join(root, 'src', 'Example.java')));
  assert.equal(entries[0].message, exampleViolation.message);
  assert.equal(entries[0].source, 'Architecture Governance');
  assert.equal(entries[0].code, exampleViolation.rule_id);
});
test('Windows separators in a relative backend path are handled', async t => {
  const { mapper, root } = await project(t);
  assert.equal((await mapper.prepare(root, [{ ...exampleViolation, file_path: 'src\\Example.java' }])).length, 1);
});
for (const file of ['../../outside.java', '..\\..\\outside.java', '/outside.java', 'C:\\outside.java', 'C:outside.java',
  '\\\\server\\share\\outside.java', 'file:///outside.java', 'src/Example.java:stream', 'bad\0name.java']) {
  test(`rejects unsafe source path ${JSON.stringify(file)}`, async t => {
    const { mapper, root, logs } = await project(t);
    assert.equal((await mapper.prepare(root, [{ ...exampleViolation, file_path: file }])).length, 0);
    assert.ok(logs.some(line => line.includes('rejected')));
  });
}
test('junctions leading outside the selected root are rejected', async t => {
  const { mapper, root, temporary, logs } = await project(t);
  const outside = path.join(temporary, 'other-project');
  await fs.mkdir(outside);
  await fs.writeFile(path.join(outside, 'Other.java'), 'class Other {}');
  await fs.symlink(outside, path.join(root, 'linked'), process.platform === 'win32' ? 'junction' : 'dir');
  assert.equal((await mapper.prepare(root, [{ ...exampleViolation, file_path: 'linked/Other.java' }])).length, 0);
  assert.ok(logs.some(line => line.includes('linked source outside')));
});
test('missing file and missing location do not fail other violations', async t => {
  const { mapper, root, logs } = await project(t);
  const entries = await mapper.prepare(root, [{ ...exampleViolation, violation_id: 'missing', file_path: 'gone.java' },
    { ...exampleViolation, violation_id: 'no-location', start_line: undefined, end_line: undefined }, exampleViolation]);
  assert.equal(entries.length, 1);
  assert.ok(logs.some(line => line.includes('missing')) && logs.some(line => line.includes('invalid source line')));
});
test('source is resolved within the selected root when another workspace has the same relative path', async t => {
  const { mapper, root, temporary } = await project(t);
  const other = path.join(temporary, 'other-project');
  await fs.mkdir(path.join(other, 'src'), { recursive: true });
  await fs.writeFile(path.join(other, 'src', 'Example.java'), 'other file');
  assert.equal((await mapper.prepare(root, [exampleViolation]))[0].filePath, await fs.realpath(path.join(root, 'src', 'Example.java')));
});
test('source disappearance after checking is detected when navigating', async t => {
  const { mapper, root } = await project(t);
  assert.equal((await mapper.prepare(root, [exampleViolation])).length, 1);
  await fs.unlink(path.join(root, 'src', 'Example.java'));
  assert.equal(await mapper.locate(root, exampleViolation), undefined);
});
