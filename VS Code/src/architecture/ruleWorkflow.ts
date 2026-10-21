import { ArchitectureBackend, BackendApiError } from './backendClient';
import { ApprovalResponse, ConflictResponse, GeneratedRuleResponse, isRuleEnvelope } from './contracts';

export type ApprovalOutcome = { cancelled: true } | { cancelled: false; approval: ApprovalResponse };

export class ArchitectureRuleWorkflow {
  proposal: GeneratedRuleResponse | undefined;
  private proposalBackend: string | undefined;
  private saved: ApprovalResponse | undefined;

  constructor(private readonly backend: ArchitectureBackend) {}

  get canApprove(): boolean {
    return !this.saved && !!this.proposal?.json_valid && this.proposal.schema_valid
      && isRuleEnvelope(this.proposal.rule) && this.proposal.rule.status === 'VALID';
  }
  clear(): void { this.proposal = undefined; this.proposalBackend = undefined; this.saved = undefined; }

  async generate(requirement: string): Promise<GeneratedRuleResponse> {
    this.clear();
    const trimmed = requirement.trim();
    if (!trimmed) { throw new BackendApiError('input', 'Enter an architecture rule first.'); }
    const baseUrl = this.backend.baseUrl;
    const result = await this.backend.generateRule(trimmed);
    this.proposal = result;
    this.proposalBackend = baseUrl;
    this.checkBackend();
    return result;
  }

  private checkBackend(): void {
    // A proposal from one service must not be saved to another after settings change.
    if (this.proposalBackend !== this.backend.baseUrl) {
      this.clear();
      throw new BackendApiError('configuration', 'The architecture backend URL changed. Generate the interpretation again before approval.');
    }
  }

  async approve(confirm: (conflicts: ConflictResponse) => Promise<boolean>): Promise<ApprovalOutcome> {
    if (!this.proposal) { throw new BackendApiError('input', 'Generate a schema-valid VALID rule before approving.'); }
    this.checkBackend();
    if (this.saved) { return { cancelled: false, approval: this.saved }; }
    if (!this.canApprove || !isRuleEnvelope(this.proposal?.rule) || this.proposal.rule.status !== 'VALID') {
      throw new BackendApiError('input', 'Generate a schema-valid VALID rule before approving.');
    }
    const rule = this.proposal.rule;
    const conflicts = await this.backend.checkConflicts(rule);
    let confirmed = false;
    if (conflicts.has_conflict && !conflicts.duplicate) {
      if (!await confirm(conflicts)) { return { cancelled: true }; }
      confirmed = true;
    }
    this.checkBackend();
    let approval: ApprovalResponse;
    try { approval = await this.backend.approveRule(rule, confirmed); } catch (error) {
      // Another rule may be approved after the pre-check; the backend's final 409 remains authoritative.
      if (!(error instanceof BackendApiError) || error.status !== 409 || !error.conflicts?.has_conflict || confirmed) { throw error; }
      if (!await confirm(error.conflicts)) { return { cancelled: true }; }
      this.checkBackend();
      approval = await this.backend.approveRule(rule, true);
    }
    if (!approval.approved) { throw new BackendApiError('invalid-response', 'The backend did not approve the rule.'); }
    this.saved = approval;
    return { cancelled: false, approval };
  }
}
