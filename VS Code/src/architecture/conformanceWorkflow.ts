import { ProjectAnalysisWorkflow } from './analysisWorkflow';
import { BackendApiError, BackendLogger, ConformanceBackend, friendlyError } from './backendClient';
import { ConformanceResponse } from './contracts';
import { ProjectContextSyncWorkflow } from './contextSyncWorkflow';
import { ConformanceDiagnostics } from './conformanceSources';
import { canCheckConformance } from './conformanceEligibility';

export type ConformanceState = { status: 'not-checked' | 'stale' | 'checking' | 'cancelled'; message?: string }
  | { status: 'failed'; message: string }
  | { status: 'checked'; result: ConformanceResponse; navigableViolationIds: string[] };
export interface ConformanceHost { progress(task: () => Promise<void>, cancel: () => void): Promise<void>; }

export class ConformanceWorkflow {
  state: ConformanceState = { status: 'not-checked' };
  private active: Promise<void> | undefined;
  private cancellation: AbortController | undefined;
  private revision = 0;
  private disposed = false;
  private synchronizedUrl: string | undefined;
  private listeners = new Set<(state: ConformanceState) => void>();
  private readonly unsubscribeAnalysis: () => void;
  private readonly unsubscribeSync: () => void;

  constructor(private readonly analysis: ProjectAnalysisWorkflow, private readonly sync: ProjectContextSyncWorkflow,
    private readonly backend: ConformanceBackend, private readonly diagnostics: ConformanceDiagnostics,
    private readonly output: BackendLogger, private readonly host: ConformanceHost = { progress: task => task() }) {
    this.synchronizedUrl = sync.state.status === 'synchronized' ? this.configuredUrl() : undefined;
    this.unsubscribeAnalysis = analysis.subscribe(state => {
      if (state.status === 'selecting' || state.status === 'succeeded') { this.invalidate('Project analysis changed. Sync context and check again.'); }
    });
    let previous = sync.state;
    this.unsubscribeSync = sync.subscribe(state => {
      if (state !== previous) {
        this.synchronizedUrl = state.status === 'synchronized' ? this.configuredUrl() : undefined;
        this.invalidate('Project context changed. Check conformance after synchronization.');
      } else {
        // Sync also emits after clearing its active promise. Refresh eligibility without invalidating again.
        this.update(this.state);
      }
      previous = state;
    });
  }
  get isRunning(): boolean { return !!this.active || this.state.status === 'checking'; }
  get canCheck(): boolean {
    const synchronizedProject = !this.disposed && this.analysis.state.status === 'succeeded'
      && this.sync.state.status === 'synchronized'
      && !!this.synchronizedUrl && this.synchronizedUrl === this.configuredUrl();
    return canCheckConformance(synchronizedProject, this.sync.isRunning, this.isRunning);
  }
  private configuredUrl(): string | undefined {
    try { return this.backend.baseUrl; } catch { return undefined; }
  }
  subscribe(listener: (state: ConformanceState) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
  private update(state: ConformanceState): void {
    this.state = state;
    if (!this.disposed) { for (const listener of this.listeners) { listener(state); } }
  }
  invalidate(message = 'Approved rules changed. Check conformance again.'): void {
    this.revision++;
    this.cancellation?.abort();
    this.diagnostics.clear();
    this.update({ status: this.state.status === 'not-checked' ? 'not-checked' : 'stale', message });
  }
  clear(): void { this.invalidate(); this.update({ status: 'not-checked', message: 'Results cleared.' }); }
  cancel(): void {
    if (!this.isRunning) { return; }
    this.invalidate();
    this.output.appendLine('Architecture conformance check cancelled.');
    this.update({ status: 'cancelled', message: 'Architecture conformance check cancelled.' });
  }
  run(): Promise<void> {
    if (this.disposed) { return Promise.resolve(); }
    if (this.active) { return this.active; }
    this.active = this.perform().finally(() => { this.active = undefined; this.update(this.state); });
    return this.active;
  }
  private async perform(): Promise<void> {
    const revision = this.revision;
    this.diagnostics.clear();
    try {
      if (this.analysis.state.status !== 'succeeded') { throw new BackendApiError('input', 'Analyze a project before checking architecture conformance.'); }
      if (this.sync.state.status !== 'synchronized' || this.sync.isRunning) { throw new BackendApiError('input', 'Sync Project Context before checking architecture conformance.'); }
      const summary = this.analysis.state.summary;
      const url = this.backend.baseUrl;
      if (url !== this.synchronizedUrl) { throw new BackendApiError('input', 'Backend changed. Sync Project Context again before checking conformance.'); }
      this.cancellation = new AbortController();
      const signal = this.cancellation.signal;
      this.update({ status: 'checking' });
      this.output.appendLine(`Checking conformance for ${JSON.stringify(summary.projectName)}: ${summary.projectRoot}`);
      await this.host.progress(async () => {
        if (signal.aborted) { return; }
        const result = await this.backend.checkConformance(signal);
        if (!this.current(revision, url)) { return; }
        if (result.project_name !== summary.projectName) {
          this.sync.reset();
          this.update({ status: 'failed', message: 'The backend active project differs from the selected project. Sync Project Context again.' });
          return;
        }
        const entries = await this.diagnostics.prepare(summary.projectRoot, result.violations);
        // A scan, sync, rule approval or cancellation during filesystem checks must not publish old results.
        if (!this.current(revision, url)) { return; }
        this.diagnostics.replace(entries);
        this.output.appendLine(`Conformance result: ${result.summary.total} violations; ${entries.length} diagnostics created.`);
        this.update({ status: 'checked', result, navigableViolationIds: entries.map(entry => entry.violationId) });
      }, () => this.cancel());
    } catch (error) {
      if (revision !== this.revision || this.disposed) { return; }
      this.diagnostics.clear();
      const message = friendlyError(error);
      this.output.appendLine(`Conformance check failed: ${error instanceof Error ? error.message : String(error)}`);
      this.update(error instanceof BackendApiError && error.kind === 'cancelled' ? { status: 'cancelled', message } : { status: 'failed', message });
    } finally { this.cancellation = undefined; }
  }
  private current(revision: number, url: string): boolean {
    if (this.disposed || revision !== this.revision) { return false; }
    if (url !== this.backend.baseUrl) { this.invalidate('Backend changed. Sync context and check again.'); return false; }
    return true;
  }
  async navigate(violationId: string): Promise<boolean> {
    if (this.state.status !== 'checked' || this.analysis.state.status !== 'succeeded') { return false; }
    const violation = this.state.result.violations.find(item => item.violation_id === violationId);
    if (!violation) { return false; }
    try { return await this.diagnostics.open(this.analysis.state.summary.projectRoot, violation); }
    catch (error) { this.output.appendLine(`Cannot open violation source: ${error instanceof Error ? error.message : String(error)}`); return false; }
  }
  dispose(): void {
    this.disposed = true;
    this.invalidate();
    this.unsubscribeAnalysis();
    this.unsubscribeSync();
    this.listeners.clear();
  }
}
