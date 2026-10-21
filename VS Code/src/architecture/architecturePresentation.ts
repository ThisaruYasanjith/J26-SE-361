import type * as vscode from 'vscode';
import { ConformanceResponse, isRuleEnvelope, ValidRuleEnvelope } from './contracts';

export type ArchitectureUiMode = 'product' | 'developer';
export function architectureUiMode(value: unknown): ArchitectureUiMode {
  return value === 'developer' ? 'developer' : 'product';
}

export function violationSummary(result: ConformanceResponse) {
  // These are display categories only. Keep the backend's findings and total unchanged.
  const structure = result.violations.filter(item => result.rule_metadata[item.rule_id].rule_type === 'PACKAGE_PLACEMENT'
    || ['LOCATED_IN', 'CONTAINS', 'EXTENDS', 'IMPLEMENTS'].includes(item.relationship ?? '')).length;
  return { total: result.summary.total, dependency: result.violations.length - structure, structure };
}

export class ApprovedRuleViewCache {
  private readonly memory = new Map<string, ValidRuleEnvelope[]>();
  constructor(private readonly storage: vscode.Memento) {}

  read(scope: string): ValidRuleEnvelope[] {
    if (this.memory.has(scope)) { return this.memory.get(scope)!; }
    const stored = this.storage.get<unknown>('architectureGovernance.approvedRuleView:' + scope);
    const rules = Array.isArray(stored) ? stored.filter((item): item is ValidRuleEnvelope =>
      isRuleEnvelope(item) && item.status === 'VALID' && typeof item.rule_id === 'string' && !!item.rule_id.trim()) : [];
    this.memory.set(scope, rules);
    return rules;
  }

  async record(scope: string, rule: ValidRuleEnvelope, ruleId: string): Promise<void> {
    // This remembers confirmed approvals for display; the backend remains the rule store.
    const rules = [...this.read(scope).filter(item => item.rule_id !== ruleId), { ...rule, rule_id: ruleId }];
    this.memory.set(scope, rules);
    await this.storage.update('architectureGovernance.approvedRuleView:' + scope, rules);
  }
}
