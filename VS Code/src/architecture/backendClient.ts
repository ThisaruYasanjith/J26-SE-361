import {
  ApprovalResponse, ConflictResponse, GeneratedRuleResponse, ValidRuleEnvelope, ValidationError,
  isApprovalResponse, isConflictResponse, isGeneratedResponse, isRecord, isValidationError,
  ProjectContext, ProjectContextSyncResponse, isContextSyncResponse,
  ConformanceResponse, isConformanceResponse, normalizeConformanceEvidence,
} from './contracts';

export const DEFAULT_BACKEND_URL = 'http://127.0.0.1:8000';
export type BackendErrorKind = 'configuration' | 'input' | 'network' | 'timeout' | 'cancelled' | 'http' | 'invalid-response';
export interface BackendLogger { appendLine(message: string): void; }
export interface ArchitectureBackend {
  readonly baseUrl: string;
  generateRule(requirement: string): Promise<GeneratedRuleResponse>;
  checkConflicts(rule: ValidRuleEnvelope): Promise<ConflictResponse>;
  approveRule(rule: ValidRuleEnvelope, confirmConflicts?: boolean): Promise<ApprovalResponse>;
}
export interface ContextSyncBackend {
  readonly baseUrl: string;
  syncProjectContext(context: ProjectContext): Promise<ProjectContextSyncResponse>;
}
export interface ConformanceBackend {
  readonly baseUrl: string;
  checkConformance(signal?: AbortSignal): Promise<ConformanceResponse>;
}
export class BackendApiError extends Error {
  constructor(public readonly kind: BackendErrorKind, message: string, public readonly status?: number,
    public readonly conflicts?: ConflictResponse, public readonly validationErrors: ValidationError[] = []) {
    super(message);
    this.name = 'BackendApiError';
  }
}
export function normalizeBaseUrl(raw: string): string {
  try {
    const url = new URL(raw.trim());
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) { throw new Error(); }
    return url.toString().replace(/\/+$/, '');
  } catch {
    throw new BackendApiError('configuration', 'Set architectureGovernance.aiBackendUrl to an HTTP(S) base URL without credentials, query parameters or fragments.');
  }
}
export function friendlyError(error: unknown): string {
  return error instanceof BackendApiError ? error.message : 'Architecture request failed. See the Architecture Governance output channel.';
}

export class ArchitectureBackendClient implements ArchitectureBackend, ContextSyncBackend, ConformanceBackend {
  private readonly requests = new Set<AbortController>();
  private disposed = false;

  constructor(private readonly readConfiguredUrl: () => string, private readonly output: BackendLogger,
    private readonly fetchRequest: typeof fetch = globalThis.fetch, private readonly timeoutMs = 300_000) {}

  get baseUrl(): string { return normalizeBaseUrl(this.readConfiguredUrl()); }

  generateRule(requirement: string): Promise<GeneratedRuleResponse> {
    const trimmed = requirement.trim();
    if (!trimmed) { throw new BackendApiError('input', 'Enter an architecture rule first.'); }
    return this.request('POST', '/rules/generate', { requirement: trimmed, use_rag: true }, isGeneratedResponse);
  }
  checkConflicts(rule: ValidRuleEnvelope): Promise<ConflictResponse> {
    return this.request('POST', '/rules/check-conflicts', { rule }, isConflictResponse);
  }
  approveRule(rule: ValidRuleEnvelope, confirmConflicts = false): Promise<ApprovalResponse> {
    return this.request('POST', '/rules/approve', { rule, confirm_conflicts: confirmConflicts }, isApprovalResponse);
  }
  syncProjectContext(context: ProjectContext): Promise<ProjectContextSyncResponse> {
    this.output.appendLine(`Sync project ${JSON.stringify(context.project_name)}: ${context.components.length} components, ${context.relationships.length} relationships`);
    return this.request('PUT', '/context/project', context, isContextSyncResponse);
  }
  checkConformance(signal?: AbortSignal): Promise<ConformanceResponse> {
    return this.request('POST', '/conformance/check', undefined, isConformanceResponse, signal, normalizeConformanceEvidence);
  }
  dispose(): void {
    this.disposed = true;
    for (const request of this.requests) { request.abort(); }
  }

  private async request<T>(method: 'POST' | 'PUT', path: string, payload: unknown, accepts: (value: unknown) => value is T,
    signal?: AbortSignal, normalize: (value: unknown) => unknown = value => value): Promise<T> {
    if (this.disposed || signal?.aborted) { throw new BackendApiError('cancelled', 'Architecture request cancelled.'); }
    const baseUrl = this.baseUrl;
    this.output.appendLine(`${method} ${baseUrl}${path}`);
    const controller = new AbortController();
    const cancel = () => controller.abort();
    signal?.addEventListener('abort', cancel, { once: true });
    this.requests.add(controller);
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, this.timeoutMs);
    try {
      const response = await this.fetchRequest(`${baseUrl}${path}`, {
        method, headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify(payload), signal: controller.signal, redirect: 'error',
      });
      this.output.appendLine(`${path}: HTTP ${response.status}`);
      let data: unknown;
      try { data = await response.json(); } catch (error) {
        if (controller.signal.aborted) { throw error; }
        if (!response.ok) { throw new BackendApiError('http', `Architecture backend request failed (HTTP ${response.status}).`, response.status); }
        throw new BackendApiError('invalid-response', 'Architecture backend returned invalid JSON. Check the configured URL.', response.status);
      }
      if (controller.signal.aborted) { throw new Error('Architecture request aborted'); }
      if (!response.ok) {
        const conflicts = response.status === 409 && isConflictResponse(data) ? data : undefined;
        const errors = isRecord(data) && Array.isArray(data.validation_errors) ? data.validation_errors.filter(isValidationError)
          : isRecord(data) && Array.isArray(data.detail) ? data.detail.filter(item => isRecord(item) && Array.isArray(item.loc) && typeof item.msg === 'string')
            .map(item => ({ path: item.loc.join('.'), message: item.msg } as ValidationError)) : [];
        for (const issue of errors) { this.output.appendLine(`Validation failure at ${issue.path}`); }
        if (conflicts) { this.output.appendLine(`Conflicts: ${conflicts.conflicts.map(item => item.existing_rule_id).join(', ')}`); }
        const detail = isRecord(data) && typeof data.detail === 'string' ? data.detail.split(/\r?\n/)[0].slice(0, 300) : '';
        const message = response.status >= 500 ? `Architecture backend could not complete the request (HTTP ${response.status}). See Architecture Governance output.`
          : `Architecture backend rejected the request (HTTP ${response.status}).${detail ? ` ${detail}` : ''}`;
        if (detail) { this.output.appendLine(`Backend detail: ${detail}`); }
        throw new BackendApiError('http', message, response.status, conflicts, errors);
      }
      data = normalize(data);
      if (!accepts(data)) {
        throw new BackendApiError('invalid-response', 'Architecture backend returned an unexpected response. Check the backend version and URL.', response.status);
      }
      if (isConformanceResponse(data)) {
        this.output.appendLine(`Conformance: ${JSON.stringify(data.project_name)}, ${data.summary.total} violations (${data.summary.base_rule_violations} base, ${data.summary.custom_rule_violations} custom)`);
      }
      if (isGeneratedResponse(data)) {
        this.output.appendLine(`Generation: JSON valid=${data.json_valid}, schema valid=${data.schema_valid}, validation errors=${data.validation_errors.length}`);
        for (const issue of data.validation_errors) { this.output.appendLine(`Validation failure at ${issue.path}`); }
      }
      if (isConflictResponse(data)) {
        this.output.appendLine(`Conflict check: ${data.conflicts.length} conflicts, duplicate=${data.duplicate}`);
      }
      if (isApprovalResponse(data)) {
        this.output.appendLine(`Approval: ${data.rule_id}, duplicate=${data.duplicate}, conflicts confirmed=${data.conflicts_confirmed}`);
      }
      if (isContextSyncResponse(data)) {
        this.output.appendLine(`Context synchronized: ${JSON.stringify(data.project_name)}, ${data.components} components, ${data.relationships} relationships. RAG index invalidated; next retrieval rebuilds.`);
      }
      return data;
    } catch (error) {
      if (error instanceof BackendApiError) { this.output.appendLine(error.message); throw error; }
      if (controller.signal.aborted) {
        this.output.appendLine(`${path}: ${timedOut ? 'timed out' : 'cancelled'}`);
        throw new BackendApiError(timedOut ? 'timeout' : 'cancelled', timedOut
          ? 'Architecture backend request timed out. Check the service and try again.' : 'Architecture request cancelled.');
      }
      this.output.appendLine(`Network error: ${error instanceof Error ? error.message : 'Unknown error'}`);
      throw new BackendApiError('network', 'Cannot reach the architecture backend. Check architectureGovernance.aiBackendUrl and that the service is running.');
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener('abort', cancel);
      this.requests.delete(controller);
    }
  }
}
