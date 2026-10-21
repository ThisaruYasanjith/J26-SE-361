import { ProjectAnalysisWorkflow } from './analysisWorkflow';
import { AnalyzerError, readProjectContext } from './analyzerRunner';
import { BackendApiError, BackendLogger, ContextSyncBackend, friendlyError } from './backendClient';
import { ProjectContext, ProjectContextSyncResponse } from './contracts';

export type ContextSyncState = { status: 'not-synchronized'; message?: string } | { status: 'syncing' }
  | { status: 'synchronized'; response: ProjectContextSyncResponse } | { status: 'failed'; message: string };
export class ProjectContextSyncWorkflow {
  state: ContextSyncState = { status: 'not-synchronized' };
  private active: Promise<void> | undefined;
  private revision = 0;
  private listeners = new Set<(state: ContextSyncState) => void>();
  private readonly unsubscribe: () => void;

  constructor(private readonly analysis: ProjectAnalysisWorkflow, private readonly backend: ContextSyncBackend,
    private readonly output: BackendLogger, private readonly readContext: (root: string) => Promise<ProjectContext> = readProjectContext) {
    this.unsubscribe = analysis.subscribe(state => {
      if (state.status === 'selecting' || state.status === 'succeeded') { this.reset(); }
    });
  }
  get isRunning(): boolean { return !!this.active || this.state.status === 'syncing'; }
  get canSync(): boolean { return this.analysis.state.status === 'succeeded' && !this.isRunning; }
  subscribe(listener: (state: ContextSyncState) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
  private update(state: ContextSyncState): void {
    this.state = state;
    for (const listener of this.listeners) { listener(state); }
  }
  reset(): void { this.revision++; this.update({ status: 'not-synchronized' }); }
  run(): Promise<void> {
    if (this.active) { return this.active; }
    this.active = this.perform().finally(() => { this.active = undefined; this.update(this.state); });
    return this.active;
  }
  private async perform(): Promise<void> {
    const revision = this.revision;
    try {
      if (this.analysis.state.status !== 'succeeded') {
        throw new BackendApiError('input', 'Scan Project Architecture successfully before synchronizing context.');
      }
      const root = this.analysis.state.summary.projectRoot;
      this.update({ status: 'syncing' });
      const context = await this.readContext(root);
      const backendUrl = this.backend.baseUrl;
      if (revision !== this.revision) { throw new BackendApiError('input', 'Project changed. Sync the latest context again.'); }
      const response = await this.backend.syncProjectContext(context);
      // A new scan or URL change can happen while the network request is in flight.
      if (revision !== this.revision || backendUrl !== this.backend.baseUrl) {
        this.update({ status: 'not-synchronized', message: 'Project or backend changed. Sync the latest context again.' });
        return;
      }
      if (response.project_name !== context.project_name || response.components !== context.components.length
        || response.relationships !== context.relationships.length) {
        throw new BackendApiError('invalid-response', 'The backend synchronization summary does not match the uploaded project.');
      }
      this.update({ status: 'synchronized', response });
    } catch (error) {
      const message = error instanceof AnalyzerError ? error.message : friendlyError(error);
      this.output.appendLine(`Context synchronization failed: ${error instanceof AnalyzerError ? error.details ?? error.message : error instanceof Error ? error.message : String(error)}`);
      this.update({ status: 'failed', message });
    }
  }
  dispose(): void { this.unsubscribe(); this.listeners.clear(); }
}
