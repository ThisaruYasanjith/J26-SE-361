import { AnalysisCancelled, AnalysisSummary, AnalyzerError, AnalyzerRunner, selectWorkspace, WorkspaceProject } from './analyzerRunner';

export type AnalysisState = { status: 'idle' | 'selecting' | 'running' | 'cancelled' }
  | { status: 'succeeded'; summary: AnalysisSummary } | { status: 'failed'; message: string };
export interface AnalysisHost {
  folders(): readonly WorkspaceProject[] | undefined;
  choose(folders: readonly WorkspaceProject[]): Promise<WorkspaceProject | undefined>;
  progress(task: () => Promise<AnalysisSummary>, cancel: () => void): Promise<AnalysisSummary>;
  showError(message: string): void;
}
export class ProjectAnalysisWorkflow {
  state: AnalysisState = { status: 'idle' };
  private listeners = new Set<(state: AnalysisState) => void>();
  private active: Promise<void> | undefined;
  private cancellation: AbortController | undefined;

  constructor(private readonly runner: Pick<AnalyzerRunner, 'analyze'>, private readonly host: AnalysisHost) {}

  subscribe(listener: (state: AnalysisState) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
  private update(state: AnalysisState): void {
    this.state = state;
    for (const listener of this.listeners) { listener(state); }
  }
  run(): Promise<void> {
    // Palette and panel actions share one scan, avoiding concurrent writes to the context file.
    if (this.active) { return this.active; }
    this.active = this.perform().finally(() => { this.active = undefined; });
    return this.active;
  }
  private async perform(): Promise<void> {
    this.cancellation = new AbortController();
    try {
      this.update({ status: 'selecting' });
      const project = await selectWorkspace(this.host.folders(), folders => this.host.choose(folders));
      if (this.cancellation.signal.aborted) { throw new AnalysisCancelled(); }
      this.update({ status: 'running' });
      const summary = await this.host.progress(() => this.runner.analyze(project, this.cancellation!.signal), () => this.cancellation?.abort());
      if (this.cancellation.signal.aborted) { throw new AnalysisCancelled(); }
      this.update({ status: 'succeeded', summary });
    } catch (error) {
      if (error instanceof AnalysisCancelled) { this.update({ status: 'cancelled' }); }
      else {
        const message = error instanceof AnalyzerError ? error.message : 'Architecture analysis failed. See Architecture Governance output.';
        this.update({ status: 'failed', message });
        this.host.showError(message);
      }
    } finally { this.cancellation = undefined; }
  }
  dispose(): void { this.cancellation?.abort(); this.listeners.clear(); }
}
