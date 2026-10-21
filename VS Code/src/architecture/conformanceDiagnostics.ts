import * as vscode from 'vscode';
import { BackendLogger } from './backendClient';
import { ArchitectureViolation } from './contracts';
import { ConformanceDiagnostic, ConformanceDiagnostics, ConformanceSourceMapper } from './conformanceSources';

export class VscodeConformanceDiagnostics implements ConformanceDiagnostics, vscode.Disposable {
  private readonly collection = vscode.languages.createDiagnosticCollection('architectureGovernance');
  private readonly sources: ConformanceSourceMapper;
  private disposed = false;
  constructor(output: BackendLogger) { this.sources = new ConformanceSourceMapper(output); }
  clear(): void { if (!this.disposed) { this.collection.clear(); } }
  prepare(root: string, violations: ArchitectureViolation[]): Promise<ConformanceDiagnostic[]> { return this.sources.prepare(root, violations); }
  replace(entries: ConformanceDiagnostic[]): void {
    if (this.disposed) { return; }
    const grouped = new Map<string, vscode.Diagnostic[]>();
    for (const entry of entries) {
      const diagnostic = new vscode.Diagnostic(this.range(entry), entry.message, entry.severity);
      diagnostic.source = entry.source;
      diagnostic.code = entry.code;
      const group = grouped.get(entry.filePath) ?? [];
      group.push(diagnostic);
      grouped.set(entry.filePath, group);
    }
    this.collection.clear();
    this.collection.set([...grouped].map(([file, diagnostics]) => [vscode.Uri.file(file), diagnostics]));
  }
  async open(root: string, violation: ArchitectureViolation): Promise<boolean> {
    if (this.disposed) { return false; }
    // Recheck paths and existence at click time, rather than trusting the webview or an earlier result.
    const entry = await this.sources.locate(root, violation);
    if (!entry) { return false; }
    const document = await vscode.workspace.openTextDocument(vscode.Uri.file(entry.filePath));
    const range = document.validateRange(this.range(entry));
    const editor = await vscode.window.showTextDocument(document, { selection: range, preview: true });
    editor.revealRange(range, vscode.TextEditorRevealType.InCenter);
    return true;
  }
  private range(entry: ConformanceDiagnostic): vscode.Range {
    const range = entry.range;
    return new vscode.Range(range.startLine, range.startCharacter, range.endLine, range.endCharacter);
  }
  dispose(): void { this.disposed = true; this.collection.dispose(); }
}
