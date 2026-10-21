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
