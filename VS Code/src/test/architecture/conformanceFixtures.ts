import { ArchitectureViolation, ConformanceResponse } from '../../architecture/contracts';

export const exampleViolation: ArchitectureViolation = {
  violation_id: 'VIOLATION_001', rule_id: 'LAYER_CONTROLLER_REPOSITORY_DENY', severity: 'ERROR',
  message: 'AdminController must not depend directly on PaymentRepository.',
  source: 'demo.controller.AdminController', target: 'demo.repository.PaymentRepository', relationship: 'DEPENDS_ON',
  file_path: 'src/Example.java', start_line: 1, end_line: 1,
  explanation: 'A prohibited dependency was found.', suggested_correction: 'Access the repository through a service.',
};
export function conformanceResponse(violations: ArchitectureViolation[] = [exampleViolation]): ConformanceResponse {
  const base = violations.filter(item => !item.rule_id.startsWith('CUSTOM_')).length;
  return { project_name: 'payments', conformant: violations.length === 0, violations,
    summary: { total: violations.length, base_rule_violations: base, custom_rule_violations: violations.length - base },
    rule_metadata: Object.fromEntries(violations.map(item => [item.rule_id, {
      rule_type: item.relationship === 'LOCATED_IN' ? 'PACKAGE_PLACEMENT' : 'COMPONENT_ACCESS',
      rule_source: item.rule_id.startsWith('CUSTOM_') ? 'CUSTOM' : 'BASE',
    }])),
  };
}
