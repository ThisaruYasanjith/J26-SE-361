import * as assert from 'node:assert/strict';
import { test } from 'node:test';
import { AnalysisHost, ProjectAnalysisWorkflow } from '../../architecture/analysisWorkflow';
import { AnalysisCancelled, AnalysisSummary, AnalyzerError, WorkspaceProject } from '../../architecture/analyzerRunner';

const project: WorkspaceProject = { name: 'project', fsPath: '/project', scheme: 'file' };
const summary: AnalysisSummary = { projectRoot: '/project', contextPath: '/project/.architecture/project_context.json', projectName: 'project', componentCount: 7, relationshipCount: 15 };
function host() {
  const errors: string[] = [];
  const ui: AnalysisHost = {
    folders: () => [project], choose: async folders => folders[0], progress: async task => task(), showError: message => errors.push(message),
  };
  return { ui, errors };
}
test('workflow selects a workspace, shows progress and retains the summary', async () => {
  const { ui, errors } = host();
  let progress = 0;
  ui.progress = async task => { progress++; return task(); };
  const workflow = new ProjectAnalysisWorkflow({ analyze: async folder => { assert.equal(folder, project); return summary; } }, ui);
  const states: string[] = [];
  workflow.subscribe(state => states.push(state.status));
  await workflow.run();
  assert.deepEqual(states, ['selecting', 'running', 'succeeded']);
  assert.deepEqual(workflow.state, { status: 'succeeded', summary });
  assert.equal(progress, 1);
  assert.deepEqual(errors, []);
});
test('no workspace produces an error without running the analyzer', async () => {
  const { ui, errors } = host(); ui.folders = () => [];
  const workflow = new ProjectAnalysisWorkflow({ analyze: async () => { throw new Error('Must not execute'); } }, ui);
  await workflow.run();
  assert.equal(workflow.state.status, 'failed');
  assert.match(errors[0], /Open a Java project/);
});
test('cancelled multi-root selection is not a failure', async () => {
  const { ui, errors } = host(); ui.folders = () => [project, { ...project, name: 'second' }]; ui.choose = async () => undefined;
  const workflow = new ProjectAnalysisWorkflow({ analyze: async () => { throw new Error('Must not execute'); } }, ui);
  await workflow.run();
  assert.deepEqual(workflow.state, { status: 'cancelled' });
  assert.deepEqual(errors, []);
});
test('progress cancellation reaches the runner and is reported cleanly', async () => {
  const { ui, errors } = host();
  ui.progress = async (task, cancel) => { cancel(); return task(); };
  const workflow = new ProjectAnalysisWorkflow({ analyze: async (_project, signal) => {
    assert.ok(signal?.aborted); throw new AnalysisCancelled();
  } }, ui);
  await workflow.run();
  assert.deepEqual(workflow.state, { status: 'cancelled' });
  assert.deepEqual(errors, []);
});
test('failed analysis does not expose raw error stacks', async () => {
  const { ui, errors } = host();
  const workflow = new ProjectAnalysisWorkflow({ analyze: async () => { throw new AnalyzerError('execution', 'Analyzer failed.'); } }, ui);
  await workflow.run();
  assert.deepEqual(workflow.state, { status: 'failed', message: 'Analyzer failed.' });
  assert.deepEqual(errors, ['Analyzer failed.']);
});
test('palette and panel calls share a single active scan', async () => {
  const { ui } = host();
  let finish: (result: AnalysisSummary) => void = () => {};
  let count = 0;
  const workflow = new ProjectAnalysisWorkflow({ analyze: async () => {
    count++; return new Promise<AnalysisSummary>(resolve => { finish = resolve; });
  } }, ui);
  const first = workflow.run();
  assert.equal(workflow.run(), first);
  await new Promise<void>(resolve => setImmediate(resolve));
  assert.equal(count, 1);
  finish(summary);
  await first;
});
