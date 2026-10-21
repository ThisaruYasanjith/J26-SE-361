import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import { ArchitectureViolation, SourceLocation, ViolationSeverity } from './contracts';
import { BackendLogger } from './backendClient';

export interface DiagnosticRange { startLine: number; startCharacter: number; endLine: number; endCharacter: number; }
export interface ConformanceDiagnostic {
  violationId: string; filePath: string; range: DiagnosticRange; severity: number;
  message: string; code: string; source: 'Architecture Governance';
}
export interface ConformanceDiagnostics {
  clear(): void;
  prepare(root: string, violations: ArchitectureViolation[]): Promise<ConformanceDiagnostic[]>;
  replace(entries: ConformanceDiagnostic[]): void;
  open(root: string, violation: ArchitectureViolation): Promise<boolean>;
}
export function diagnosticSeverity(severity: ViolationSeverity): number {
  // VS Code uses Error=0, Warning=1 and Information=2; the backend has no hint severity.
  return { ERROR: 0, WARNING: 1, INFO: 2 }[severity];
}
export function diagnosticRange(location: SourceLocation, lines: readonly string[]): DiagnosticRange | undefined {
  const start = location.start_line;
  const end = location.end_line ?? start;
  if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start! < 1 || end! < start! || start! > lines.length) { return undefined; }
  const endLine = Math.min(end!, lines.length) - 1;
  return { startLine: start! - 1, startCharacter: 0, endLine, endCharacter: lines[endLine].length };
}
function inside(root: string, file: string): boolean {
  const relative = path.relative(root, file);
  return relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
}

export class ConformanceSourceMapper {
  constructor(private readonly output: BackendLogger) {}

  async prepare(root: string, violations: ArchitectureViolation[]): Promise<ConformanceDiagnostic[]> {
    const cache = new Map<string, string[]>();
    const entries = [];
    for (const violation of violations) {
      const entry = await this.locate(root, violation, cache);
      if (entry) { entries.push(entry); }
    }
    return entries;
  }
  async locate(root: string, violation: ArchitectureViolation, cache = new Map<string, string[]>()): Promise<ConformanceDiagnostic | undefined> {
    const file = violation.file_path;
    const skip = (reason: string) => this.output.appendLine(`Skipping source for ${JSON.stringify(violation.violation_id)} (${file ? JSON.stringify(file) : 'no path'}): ${reason}`);
    if (typeof file !== 'string' || !file.trim()) { skip('missing source path'); return; }
    // Accept project-relative filesystem paths only, including on a different host OS.
    if (file.includes('\0') || file.includes(':') || path.isAbsolute(file) || path.win32.isAbsolute(file)) {
      skip('rejected absolute/invalid source path'); return;
    }
    const candidate = path.resolve(root, file.replace(/\\/g, '/'));
    if (!inside(path.resolve(root), candidate)) { skip('rejected path outside selected project'); return; }
    try {
      const canonicalRoot = await fs.realpath(root);
      const canonicalFile = await fs.realpath(candidate);
      if (!inside(canonicalRoot, canonicalFile)) { skip('rejected linked source outside selected project'); return; }
      if (!(await fs.stat(canonicalFile)).isFile()) { skip('source is not a file'); return; }
      let lines = cache.get(canonicalFile);
      if (!lines) {
        lines = (await fs.readFile(canonicalFile, 'utf8')).split(/\r\n|\n|\r/);
        cache.set(canonicalFile, lines);
      }
      const range = diagnosticRange(violation, lines);
      if (!range) { skip('missing or invalid source line range'); return; }
      return { violationId: violation.violation_id, filePath: canonicalFile, range,
        severity: diagnosticSeverity(violation.severity), message: violation.message, code: violation.rule_id, source: 'Architecture Governance' };
    } catch (error) {
      skip(`file missing or unreadable (${(error as NodeJS.ErrnoException).code ?? 'filesystem error'})`);
      return;
    }
  }
}
