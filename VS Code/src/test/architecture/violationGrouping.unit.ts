import * as assert from 'node:assert/strict';
import { test, TestContext } from 'node:test';
import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { activeProjectJavaFile, groupViolations, normalizeViolationPath } from '../../architecture/violationGrouping';
import { exampleViolation } from './conformanceFixtures';

const identity = async (file: string) => file;
function document(file: string, languageId = 'java', scheme = 'file', isUntitled = false) {
  return { uri: { fsPath: file, scheme }, languageId, isUntitled };
}

test('active Java file becomes a normalized project-relative path', async () => {
  assert.deepEqual(await activeProjectJavaFile('/project', document('/project/src/./main/Example.java'), identity, 'linux'),
    { filePath: 'src/main/Example.java', fileName: 'Example.java' });
});
test('Windows paths match different separators and casing without losing the display filename', async () => {
  const active = await activeProjectJavaFile('C:\\Project', document('c:\\project\\SRC\\Example.java'), identity, 'win32');
  assert.deepEqual(active, { filePath: 'SRC/Example.java', fileName: 'Example.java' });
  const violation = { ...exampleViolation, file_path: '.\\src\\.\\EXAMPLE.java' };
  assert.deepEqual(groupViolations([violation], active, 'win32').currentFileViolations, [violation]);
});
test('case-sensitive hosts do not merge distinct filenames', () => {
  const groups = groupViolations([exampleViolation], { filePath: 'src/example.java', fileName: 'example.java' }, 'linux');
  assert.equal(groups.currentFileViolations.length, 0);
});
for (const active of [undefined, document('/project/readme.md', 'markdown'), document('/project/Example.java', 'plaintext'),
  document('/other/Example.java'), document('/project-other/Example.java'), document('/project/Example.java', 'java', 'untitled', true),
  document('/project/settings.json', 'jsonc'), document('/project/Example.java', 'java', 'output')]) {
  test('irrelevant or outside editors use the project-wide view', async () => {
    assert.equal(await activeProjectJavaFile('/project', active, identity, 'linux'), undefined);
  });
}
test('a missing file or filesystem error falls back to project-wide view', async () => {
  assert.equal(await activeProjectJavaFile('/project', document('/project/Example.java'), async () => { throw new Error('missing'); }, 'linux'), undefined);
});
test('a linked Java file outside the project is not selected', async () => {
  assert.equal(await activeProjectJavaFile('/project', document('/project/linked/Example.java'),
    async file => file === '/project' ? '/project' : '/outside/Example.java', 'linux'), undefined);
});
test('same basename in main and test directories stays separate and each violation appears once', () => {
  const other = { ...exampleViolation, violation_id: 'OTHER', file_path: 'src/test/Example.java' };
  const input = [other, exampleViolation];
  const grouped = groupViolations(input, { filePath: './src/Example.java', fileName: 'Example.java' }, 'linux');
  assert.deepEqual(grouped.currentFileViolations, [exampleViolation]);
  assert.deepEqual(grouped.otherViolations, [other]);
  assert.equal(new Set([...grouped.currentFileViolations, ...grouped.otherViolations].map(item => item.violation_id)).size, 2);
  assert.deepEqual(input, [other, exampleViolation]);
});
test('no active file leaves the complete cached list in its original order', () => {
  const result = groupViolations([exampleViolation], undefined);
  assert.deepEqual(result, { currentFileViolations: [], otherViolations: [exampleViolation] });
});
test('switching files changes the groups without changing the cached violations', () => {
  const second = { ...exampleViolation, violation_id: 'SECOND', file_path: 'src/Other.java' };
  const violations = [exampleViolation, second];
  assert.deepEqual(groupViolations(violations, { filePath: 'src/Example.java', fileName: 'Example.java' }).currentFileViolations, [exampleViolation]);
  assert.deepEqual(groupViolations(violations, { filePath: 'src/Other.java', fileName: 'Other.java' }).currentFileViolations, [second]);
});
for (const invalid of ['../outside.java', 'src/../../outside.java', 'C:\\Example.java', '/Example.java', 'file:Example.java', undefined]) {
  test('unsafe violation paths cannot become current-file matches', () => {
    assert.equal(normalizeViolationPath(invalid), undefined);
  });
}
test('real project paths are checked without reading source contents', async (t: TestContext) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'architecture-active-file-'));
  t.after(async () => {
    assert.equal(path.dirname(root), path.resolve(os.tmpdir()));
    await fs.rm(root, { recursive: true, force: true });
  });
  await fs.writeFile(path.join(root, 'Example.java'), 'class Example {}');
  assert.deepEqual(await activeProjectJavaFile(root, document(path.join(root, 'Example.java'))),
    { filePath: 'Example.java', fileName: 'Example.java' });
});
