export type RuleStatus = 'VALID' | 'AMBIGUOUS' | 'UNSUPPORTED';
export type RuleType = 'LAYER_DEPENDENCY' | 'COMPONENT_ACCESS' | 'PACKAGE_PLACEMENT' | 'EXCEPTION';
export type EntityType = 'LAYER' | 'PACKAGE' | 'CLASS' | 'INTERFACE' | 'COMPONENT';
export type Relationship = 'DEPENDS_ON' | 'CALLS' | 'IMPORTS' | 'EXTENDS' | 'IMPLEMENTS' | 'LOCATED_IN';
export type RuleAction = 'ALLOW' | 'DENY' | 'ONLY' | 'REQUIRE';
export type ReasonCode = 'MISSING_SOURCE' | 'MISSING_TARGET' | 'UNCLEAR_RELATIONSHIP' | 'UNCLEAR_SCOPE'
  | 'INSUFFICIENT_RULE_INFORMATION' | 'MULTIPLE_INTERPRETATIONS' | 'NOT_ARCHITECTURAL_CONSTRAINT' | 'UNSUPPORTED_RELATIONSHIP';

export interface RuleEntity { entity_type: EntityType; name: string; }
export interface RuleScope { type: 'PROJECT'; value: null; }
export interface ArchitectureRule {
  rule_type: RuleType;
  source: RuleEntity;
  relationship: Relationship;
  target: RuleEntity;
  action: RuleAction;
  scope: RuleScope;
  is_exception: boolean;
}
export interface ValidRuleEnvelope {
  rule_id?: string;
  status: 'VALID';
  rule: ArchitectureRule;
  reason_code: null;
}
export type ArchitectureRuleEnvelope = ValidRuleEnvelope | {
  rule_id?: string;
  status: 'AMBIGUOUS' | 'UNSUPPORTED';
  rule: null;
  reason_code: ReasonCode;
};
export interface ValidationError { path: string; message: string; }
export interface ValidationResult { valid: boolean; errors: ValidationError[]; }
export interface RetrievedContext {
  text: string;
  document_type: 'COMPONENT' | 'RELATIONSHIP' | 'BASE_RULE' | 'CUSTOM_RULE' | 'EXCEPTION';
  source_id: string;
  project_name?: string | null;
  score: number;
}
export interface GeneratedRuleResponse {
  generated_text: string;
  json_valid: boolean;
  schema_valid: boolean;
  validation_errors: ValidationError[];
  // Schema-invalid JSON is deliberately preserved by the backend, so it cannot be assumed to be a rule.
  rule: unknown;
  retrieved_context: RetrievedContext[];
}
export interface ConflictItem { existing_rule_id: string; reason: string; }
export interface ConflictResponse { has_conflict: boolean; duplicate: boolean; conflicts: ConflictItem[]; }
export interface ApprovalResponse { approved: boolean; rule_id: string; conflicts_confirmed: boolean; duplicate: boolean; }

export type ViolationSeverity = 'INFO' | 'WARNING' | 'ERROR';
export interface SourceLocation { start_line?: number | null; end_line?: number | null; }
export interface ArchitectureViolation extends SourceLocation {
  violation_id: string;
  rule_id: string;
  severity: ViolationSeverity;
  message: string;
  source: string;
  target?: string | null;
  relationship?: Relationship | 'CONTAINS' | null;
  // The backend normally supplies these fields; missing evidence must still be visible in the panel.
  file_path?: string | null;
  explanation: string;
  suggested_correction: string;
}
export interface ConformanceSummary { total: number; base_rule_violations: number; custom_rule_violations: number; }
export interface ConformanceRuleMetadata { rule_type: RuleType; rule_source: 'BASE' | 'CUSTOM'; }
export interface ConformanceResponse {
  project_name: string;
  conformant: boolean;
  violations: ArchitectureViolation[];
  summary: ConformanceSummary;
  rule_metadata: Record<string, ConformanceRuleMetadata>;
}

export function normalizeConformanceEvidence(value: unknown): unknown {
  if (!isRecord(value) || !Array.isArray(value.violations)) { return value; }
  // Keep a finding visible when only its source evidence is malformed. Never change its decision or message.
  return { ...value, violations: value.violations.map(item => {
    if (!isRecord(item)) { return item; }
    const invalidLines = !optional(item.start_line, line => typeof line === 'number')
      || !optional(item.end_line, line => typeof line === 'number');
    return { ...item, file_path: optional(item.file_path, file => typeof file === 'string') ? item.file_path : undefined,
      start_line: invalidLines ? undefined : item.start_line, end_line: invalidLines ? undefined : item.end_line };
  }) };
}

export function isConformanceResponse(value: unknown): value is ConformanceResponse {
  if (!isRecord(value) || typeof value.project_name !== 'string' || !value.project_name.trim()
    || typeof value.conformant !== 'boolean' || !Array.isArray(value.violations)
    || !isRecord(value.summary) || !isRecord(value.rule_metadata)) { return false; }
  const { summary, violations, rule_metadata: metadata } = value;
  if (![summary.total, summary.base_rule_violations, summary.custom_rule_violations]
    .every(count => Number.isSafeInteger(count) && (count as number) >= 0)
    || summary.total !== violations.length || summary.total !== (summary.base_rule_violations as number) + (summary.custom_rule_violations as number)
    || value.conformant !== (violations.length === 0)) { return false; }
  const ids = new Set<string>();
  let base = 0;
  for (const item of violations) {
    if (!isRecord(item) || !['violation_id', 'rule_id', 'message', 'source', 'explanation', 'suggested_correction']
      .every(key => typeof item[key] === 'string' && (item[key] as string).trim())
      || !member(item.severity, ['ERROR', 'WARNING', 'INFO'])
      || !optional(item.target, value => typeof value === 'string')
      || !optional(item.relationship, value => member(value, ['DEPENDS_ON', 'CALLS', 'IMPORTS', 'EXTENDS', 'IMPLEMENTS', 'CONTAINS', 'LOCATED_IN']))
      || !optional(item.file_path, value => typeof value === 'string')
      || !optional(item.start_line, value => typeof value === 'number') || !optional(item.end_line, value => typeof value === 'number')) { return false; }
    if (ids.has(item.violation_id as string)) { return false; }
    ids.add(item.violation_id as string);
    const rule = metadata[item.rule_id as string];
    if (!isRecord(rule) || !member(rule.rule_source, ['BASE', 'CUSTOM'])
      || !member(rule.rule_type, ['LAYER_DEPENDENCY', 'COMPONENT_ACCESS', 'PACKAGE_PLACEMENT', 'EXCEPTION'])) { return false; }
    if (rule.rule_source === 'BASE') { base++; }
  }
  return base === summary.base_rule_violations;
}
function optional(value: unknown, accepts: (value: unknown) => boolean): boolean {
  return value === undefined || value === null || accepts(value);
}

// The extension checks the context header; the backend validates each component and relationship in full.
export interface ProjectContext {
  schema_version: '1.0';
  project_name: string;
  project_root: string;
  components: unknown[];
  relationships: unknown[];
}
export interface ProjectContextSyncResponse {
  updated: boolean;
  project_name: string;
  components: number;
  relationships: number;
  rag_invalidated: boolean;
}
export function isProjectContext(value: unknown): value is ProjectContext {
  return isRecord(value) && value.schema_version === '1.0' && typeof value.project_name === 'string' && !!value.project_name.trim()
    && typeof value.project_root === 'string' && !!value.project_root.trim()
    && Array.isArray(value.components) && Array.isArray(value.relationships);
}
export function isContextSyncResponse(value: unknown): value is ProjectContextSyncResponse {
  return isRecord(value) && value.updated === true && value.rag_invalidated === true && typeof value.project_name === 'string'
    && !!value.project_name.trim() && Number.isInteger(value.components) && (value.components as number) >= 0
    && Number.isInteger(value.relationships) && (value.relationships as number) >= 0;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
function member(value: unknown, choices: readonly string[]): boolean {
  return typeof value === 'string' && choices.includes(value);
}
function isEntity(value: unknown): value is RuleEntity {
  return isRecord(value) && member(value.entity_type, ['LAYER', 'PACKAGE', 'CLASS', 'INTERFACE', 'COMPONENT'])
    && typeof value.name === 'string' && value.name.trim().length > 0;
}
export function isRuleEnvelope(value: unknown): value is ArchitectureRuleEnvelope {
  if (!isRecord(value) || (value.rule_id !== undefined && typeof value.rule_id !== 'string')) { return false; }
  if (value.status === 'AMBIGUOUS' || value.status === 'UNSUPPORTED') {
    return value.rule === null && member(value.reason_code, ['MISSING_SOURCE', 'MISSING_TARGET', 'UNCLEAR_RELATIONSHIP',
      'UNCLEAR_SCOPE', 'INSUFFICIENT_RULE_INFORMATION', 'MULTIPLE_INTERPRETATIONS', 'NOT_ARCHITECTURAL_CONSTRAINT', 'UNSUPPORTED_RELATIONSHIP']);
  }
  const rule = value.rule;
  return value.status === 'VALID' && value.reason_code === null && isRecord(rule)
    && member(rule.rule_type, ['LAYER_DEPENDENCY', 'COMPONENT_ACCESS', 'PACKAGE_PLACEMENT', 'EXCEPTION'])
    && isEntity(rule.source) && isEntity(rule.target)
    && member(rule.relationship, ['DEPENDS_ON', 'CALLS', 'IMPORTS', 'EXTENDS', 'IMPLEMENTS', 'LOCATED_IN'])
    && member(rule.action, ['ALLOW', 'DENY', 'ONLY', 'REQUIRE'])
    && isRecord(rule.scope) && rule.scope.type === 'PROJECT' && rule.scope.value === null
    && typeof rule.is_exception === 'boolean';
}
export function isValidationError(value: unknown): value is ValidationError {
  return isRecord(value) && typeof value.path === 'string' && typeof value.message === 'string';
}
export function isGeneratedResponse(value: unknown): value is GeneratedRuleResponse {
  if (!isRecord(value) || typeof value.generated_text !== 'string' || typeof value.json_valid !== 'boolean'
    || typeof value.schema_valid !== 'boolean' || !('rule' in value)
    || !Array.isArray(value.validation_errors) || !value.validation_errors.every(isValidationError)
    || !Array.isArray(value.retrieved_context)) { return false; }
  if (value.schema_valid && (!value.json_valid || value.validation_errors.length > 0 || !isRuleEnvelope(value.rule))) { return false; }
  if (!value.json_valid && value.rule !== null) { return false; }
  return value.retrieved_context.every(item => isRecord(item) && typeof item.text === 'string'
    && member(item.document_type, ['COMPONENT', 'RELATIONSHIP', 'BASE_RULE', 'CUSTOM_RULE', 'EXCEPTION'])
    && typeof item.source_id === 'string' && typeof item.score === 'number' && Number.isFinite(item.score)
    && (item.project_name === undefined || item.project_name === null || typeof item.project_name === 'string'));
}
export function isConflictResponse(value: unknown): value is ConflictResponse {
  return isRecord(value) && typeof value.has_conflict === 'boolean' && typeof value.duplicate === 'boolean'
    && Array.isArray(value.conflicts) && value.conflicts.every(item => isRecord(item)
      && typeof item.existing_rule_id === 'string' && typeof item.reason === 'string')
    && value.has_conflict === (value.conflicts.length > 0);
}
export function isApprovalResponse(value: unknown): value is ApprovalResponse {
  return isRecord(value) && typeof value.approved === 'boolean' && typeof value.rule_id === 'string' && value.rule_id.length > 0
    && typeof value.conflicts_confirmed === 'boolean' && typeof value.duplicate === 'boolean';
}
