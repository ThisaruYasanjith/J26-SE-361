import * as assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import { tmpdir } from 'node:os';
import { PassThrough } from 'node:stream';
import { test, TestContext } from 'node:test';
import {
  AnalysisCancelled, AnalyzerChild, AnalyzerError, AnalyzerRunner, JavaRunRequest, JavaRunResult,
  resolveAnalyzerJar, runJavaAnalyzer, selectWorkspace, WorkspaceProject,
} from '../../architecture/analyzerRunner';

const success: JavaRunResult = { exitCode: 0, signal: null, stdout: 'Java files found: 2\nSource code should not be logged\n', stderr: '' };
const context = { schema_version: '1.0', project_name: 'payments', project_root: '.', components: [{ name: 'Service' }], relationships: [{ source: 'Service', target: 'Gateway' }] };

async function fixture(t: TestContext) {
  const root = await fs.mkdtemp(path.join(tmpdir(), 'j26-analyzer-unit-'));
  t.after(async () => {
    assert.equal(path.dirname(root), path.resolve(tmpdir()));
    await fs.rm(root, { recursive: true, force: true });
  });
  const extensionRoot = path.join(root, 'VS Code');
  const project: WorkspaceProject = { name: 'sample project', fsPath: path.join(root, 'sample project & test'), scheme: 'file' };
  const jar = path.join(root, 'Architecture', 'java-analyzer', 'target', 'java-analyzer.jar');
  const contextPath = path.join(project.fsPath, '.architecture', 'project_context.json');
  await fs.mkdir(path.dirname(jar), { recursive: true });
  await fs.writeFile(jar, 'mock jar');
  await fs.mkdir(project.fsPath, { recursive: true });
  await fs.writeFile(path.join(project.fsPath, 'pom.xml'), '<project/>');
  const logs: string[] = [];
  const log = { appendLine: (message: string) => logs.push(message) };
  const writeContext = async (value: unknown = context) => {
    await fs.mkdir(path.dirname(contextPath), { recursive: true });
    await fs.writeFile(contextPath, JSON.stringify(value));
  };
  return { root, extensionRoot, project, jar, contextPath, logs, log, writeContext };
}

test('uses the single workspace without prompting', async () => {
  const folder = { name: 'project', fsPath: '/project', scheme: 'file' };
  assert.equal(await selectWorkspace([folder], async () => { throw new Error('Unexpected prompt'); }), folder);
});
test('asks for a workspace when multiple folders are open', async () => {
  const folders = [{ name: 'a', fsPath: '/a', scheme: 'file' }, { name: 'b', fsPath: '/b', scheme: 'file' }];
  assert.equal(await selectWorkspace(folders, async offered => { assert.equal(offered, folders); return offered[1]; }), folders[1]);
});
test('no workspace produces a clear error', async () => {
  await assert.rejects(selectWorkspace(undefined, async () => undefined), (error: unknown) => error instanceof AnalyzerError && error.kind === 'workspace');
});
test('dismissed workspace selection is cancellation', async () => {
  await assert.rejects(selectWorkspace([{ name: 'a', fsPath: '/a', scheme: 'file' }, { name: 'b', fsPath: '/b', scheme: 'file' }], async () => undefined), AnalysisCancelled);
});
test('rejects a folder not offered by the workspace picker', async () => {
  const folders = [{ name: 'a', fsPath: '/a', scheme: 'file' }, { name: 'b', fsPath: '/b', scheme: 'file' }];
  await assert.rejects(selectWorkspace(folders, async () => ({ name: 'other', fsPath: '/other', scheme: 'file' })), AnalyzerError);
});
test('resolves the actual Maven finalName in the monorepo', async t => {
  const f = await fixture(t);
  assert.equal(await resolveAnalyzerJar(f.extensionRoot), f.jar);
});
test('resolves a bundled JAR when the Maven artifact is absent', async t => {
  const f = await fixture(t);
  await fs.unlink(f.jar);
  const bundled = path.join(f.extensionRoot, 'dist', 'java-analyzer.jar');
  await fs.mkdir(path.dirname(bundled), { recursive: true });
  await fs.writeFile(bundled, 'mock jar');
  assert.equal(await resolveAnalyzerJar(f.extensionRoot), bundled);
});
test('a missing JAR explains how to build the analyzer', async t => {
  const f = await fixture(t);
  await fs.unlink(f.jar);
  await assert.rejects(resolveAnalyzerJar(f.extensionRoot), (error: unknown) => error instanceof AnalyzerError && error.kind === 'jar-missing' && error.message.includes('mvn package'));
});
test('successful execution returns the generated context summary and logs only stdout summary', async t => {
  const f = await fixture(t);
  const calls: JavaRunRequest[] = [];
  const runner = new AnalyzerRunner(f.extensionRoot, f.log, async request => { calls.push(request); await f.writeContext(); return success; });
  assert.deepEqual(await runner.analyze(f.project), { projectRoot: f.project.fsPath, contextPath: f.contextPath, projectName: 'payments', componentCount: 1, relationshipCount: 1 });
  assert.equal(calls[0].jarPath, f.jar);
  assert.equal(calls[0].projectRoot, f.project.fsPath);
  assert.ok(f.logs.some(line => line.includes('Java files found: 2')));
  assert.ok(!f.logs.some(line => line.includes('Source code should not be logged')));
});
test('non-zero exit is failure even if a previous context exists', async t => {
  const f = await fixture(t);
  await f.writeContext();
  const runner = new AnalyzerRunner(f.extensionRoot, f.log, async () => ({ ...success, exitCode: 1, stderr: 'Parse failure details' }));
  await assert.rejects(runner.analyze(f.project), (error: unknown) => error instanceof AnalyzerError && error.kind === 'execution');
  assert.ok(f.logs.some(line => line.includes('Parse failure details')));
});
test('exit zero without a generated context is failure', async t => {
  const f = await fixture(t);
  await assert.rejects(new AnalyzerRunner(f.extensionRoot, f.log, async () => success).analyze(f.project), /did not generate/);
});
test('malformed generated JSON is reported', async t => {
  const f = await fixture(t);
  const runner = new AnalyzerRunner(f.extensionRoot, f.log, async () => {
    await f.writeContext(); await fs.writeFile(f.contextPath, '{'); return success;
  });
  await assert.rejects(runner.analyze(f.project), /not valid JSON/);
});
for (const invalid of [null, { ...context, schema_version: '2.0' }, { ...context, project_name: '' },
  { ...context, components: {} }, { ...context, relationships: null }]) {
  test('rejects unsupported or structurally incomplete project context', async t => {
    const f = await fixture(t);
    await assert.rejects(new AnalyzerRunner(f.extensionRoot, f.log, async () => { await f.writeContext(invalid); return success; }).analyze(f.project), AnalyzerError);
  });
}
for (const marker of ['build.gradle', 'build.gradle.kts', 'src/main/java']) {
  test(`accepts lightweight Java project marker ${marker}`, async t => {
    const f = await fixture(t);
    await fs.unlink(path.join(f.project.fsPath, 'pom.xml'));
    if (marker === 'src/main/java') { await fs.mkdir(path.join(f.project.fsPath, marker), { recursive: true }); }
    else { await fs.writeFile(path.join(f.project.fsPath, marker), ''); }
    await new AnalyzerRunner(f.extensionRoot, f.log, async () => { await f.writeContext(); return success; }).analyze(f.project);
  });
}
test('rejects unrelated folders before process execution', async t => {
  const f = await fixture(t);
  await fs.unlink(path.join(f.project.fsPath, 'pom.xml'));
  await assert.rejects(new AnalyzerRunner(f.extensionRoot, f.log, async () => { throw new Error('Must not execute'); }).analyze(f.project), /does not look like a Java project/);
});
test('rejects virtual workspace folders', async t => {
  const f = await fixture(t);
  await assert.rejects(new AnalyzerRunner(f.extensionRoot, f.log).analyze({ ...f.project, scheme: 'vscode-vfs' }), /local filesystem/);
});
test('permission errors are friendly and logged', async t => {
  const f = await fixture(t);
  const files = {
    stat: async () => { throw Object.assign(new Error('Access denied'), { code: 'EACCES' }); },
    realpath: async (file: string) => file, readFile: async () => '',
  };
  await assert.rejects(new AnalyzerRunner(f.extensionRoot, f.log, async () => success, files).analyze(f.project),
    (error: unknown) => error instanceof AnalyzerError && error.kind === 'permissions');
  assert.ok(f.logs.some(line => line.includes('Access denied')));
});
test('linked context directories outside the workspace are rejected before execution', async t => {
  const f = await fixture(t);
  await fs.mkdir(path.dirname(f.contextPath), { recursive: true });
  const files = {
    stat: (file: string) => fs.stat(file), readFile: (file: string) => fs.readFile(file, 'utf8'),
    realpath: async (file: string) => file === path.dirname(f.contextPath) ? f.root : fs.realpath(file),
  };
  await assert.rejects(new AnalyzerRunner(f.extensionRoot, f.log, async () => { throw new Error('Must not execute'); }, files).analyze(f.project), /outside the selected workspace/);
});

function child() {
  const events = new EventEmitter();
  const process = Object.assign(events, { stdout: new PassThrough(), stderr: new PassThrough(), kill: (_signal?: NodeJS.Signals | number) => true });
  return process;
}
test('process invocation uses argument arrays, captures streams and preserves spaced paths', async () => {
  const process = child();
  const result = runJavaAnalyzer({ jarPath: '/extension path/java-analyzer.jar', projectRoot: '/sample & project' }, (args, cwd) => {
    assert.deepEqual(args, ['-jar', '/extension path/java-analyzer.jar', '/sample & project']);
    assert.equal(cwd, '/sample & project');
    queueMicrotask(() => { process.stdout.write('summary'); process.stderr.write('warning'); process.emit('close', 0, null); });
    return process as AnalyzerChild;
  });
  assert.deepEqual(await result, { exitCode: 0, signal: null, stdout: 'summary', stderr: 'warning' });
});
test('missing Java maps ENOENT to a useful PATH error', async () => {
  const process = child();
  await assert.rejects(runJavaAnalyzer({ jarPath: '/analyzer.jar', projectRoot: '/project' }, () => {
    queueMicrotask(() => process.emit('error', Object.assign(new Error('spawn java ENOENT'), { code: 'ENOENT' })));
    return process as AnalyzerChild;
  }), (error: unknown) => error instanceof AnalyzerError && error.kind === 'java-unavailable' && error.message.includes('PATH'));
});
test('cancellation terminates the process and waits for close', async () => {
  const process = child();
  const cancellation = new AbortController();
  const kills: (NodeJS.Signals | number | undefined)[] = [];
  process.kill = signal => { kills.push(signal); queueMicrotask(() => process.emit('close', null, 'SIGTERM')); return true; };
  const pending = runJavaAnalyzer({ jarPath: '/analyzer.jar', projectRoot: '/project', signal: cancellation.signal }, () => process as AnalyzerChild);
  cancellation.abort();
  await assert.rejects(pending, AnalysisCancelled);
  assert.deepEqual(kills, ['SIGTERM']);
});
test('already cancelled execution never starts Java', async () => {
  const cancellation = new AbortController(); cancellation.abort();
  await assert.rejects(runJavaAnalyzer({ jarPath: '/analyzer.jar', projectRoot: '/project', signal: cancellation.signal }, () => { throw new Error('Must not execute'); }), AnalysisCancelled);
});
