import * as vscode from 'vscode';
import { randomBytes } from 'node:crypto';
import { ArchitectureBackendClient, BackendApiError, DEFAULT_BACKEND_URL, friendlyError } from './backendClient';
import { isRecord } from './contracts';
import { ArchitectureRuleWorkflow } from './ruleWorkflow';
import { analysisFormHtml, architectureStyles, conformanceFormHtml, ruleFormHtml, ruleWebviewScript } from './architectureView';
import { ProjectAnalysisWorkflow } from './analysisWorkflow';
import { ProjectContextSyncWorkflow } from './contextSyncWorkflow';
import { ConformanceWorkflow } from './conformanceWorkflow';
import { activeProjectJavaFile, groupViolations } from './violationGrouping';

export class ArchitecturePanel {
  private static currentPanel: vscode.WebviewPanel | undefined;

  public static show(context: vscode.ExtensionContext, output: vscode.OutputChannel, analysis: ProjectAnalysisWorkflow,
    contextSync: ProjectContextSyncWorkflow, conformance: ConformanceWorkflow) {
    if (ArchitecturePanel.currentPanel) {
      ArchitecturePanel.currentPanel.reveal(vscode.ViewColumn.Beside);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      'architecturePanel',
      'Architecture Details',
      vscode.ViewColumn.Beside,
      { enableScripts: true, retainContextWhenHidden: true }
    );

    ArchitecturePanel.currentPanel = panel;
    const client = new ArchitectureBackendClient(
      () => vscode.workspace.getConfiguration('architectureGovernance').get<string>('aiBackendUrl', DEFAULT_BACKEND_URL), output,
    );
    const workflow = new ArchitectureRuleWorkflow(client);
    let disposed = false;
    let busy = false;
    const send = (message: unknown) => {
      if (!disposed) { void panel.webview.postMessage(message); }
    };
    const sendBackendStatus = () => {
      try { send({ type: 'backendStatus', configured: true, host: new URL(client.baseUrl).hostname }); }
      catch { send({ type: 'backendStatus', configured: false }); }
    };
    const configurationListener = vscode.workspace.onDidChangeConfiguration(event => {
      if (event.affectsConfiguration('architectureGovernance.aiBackendUrl')) { sendBackendStatus(); }
    });
    const unsubscribeAnalysis = analysis.subscribe(state => send({ type: 'analysis', state }));
    const sendSync = () => send({ type: 'contextSync', state: contextSync.state,
      canSync: contextSync.canSync, syncing: contextSync.isRunning });
    let conformanceViewRevision = 0;
    const sendConformance = async () => {
      const revision = ++conformanceViewRevision;
      const state = conformance.state;
      const root = analysis.state.status === 'succeeded' ? analysis.state.summary.projectRoot : undefined;
      const activeFile = state.status === 'checked' && root
        ? await activeProjectJavaFile(root, vscode.window.activeTextEditor?.document) : undefined;
      // Editor changes and invalidation can arrive while paths are resolving. Publish only the latest view.
      if (disposed || revision !== conformanceViewRevision || state !== conformance.state) { return; }
      send({ type: 'conformance', state, canCheck: conformance.canCheck, checking: conformance.isRunning, activeFile,
        violationGroups: state.status === 'checked' ? groupViolations(state.result.violations, activeFile) : undefined });
    };
    const unsubscribeConformance = conformance.subscribe(() => { void sendConformance(); });
    const editorListener = vscode.window.onDidChangeActiveTextEditor(() => { void sendConformance(); });
    let lastSyncState = contextSync.state;
    const unsubscribeSync = contextSync.subscribe(state => {
      // An interpretation reviewed against the previous context should be regenerated.
      if (state.status === 'synchronized' && state !== lastSyncState) {
        workflow.clear();
        send({ type: 'contextChanged' });
      }
      lastSyncState = state;
      sendSync();
    });
    const listener = panel.webview.onDidReceiveMessage(async (message: unknown) => {
      if (!isRecord(message) || disposed) { return; }
      if (message.type === 'ready') { sendBackendStatus(); send({ type: 'analysis', state: analysis.state }); sendSync(); sendConformance(); return; }
      if (message.type === 'openViolation' && typeof message.violationId === 'string') {
        if (!await conformance.navigate(message.violationId)) { void vscode.window.showWarningMessage('Architecture violation source is unavailable. See Architecture Governance output.'); }
        return;
      }
      if (message.type === 'clearConformance') { conformance.clear(); return; }
      if (busy || contextSync.isRunning || conformance.isRunning) { return; }
      if (message.type === 'checkConformance') { await conformance.run(); return; }
      if (message.type === 'scan') { await analysis.run(); return; }
      if (message.type === 'sync') {
        await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification,
          title: 'Synchronizing project architecture context...' }, async () => contextSync.run());
        return;
      }
      if (analysis.state.status === 'selecting' || analysis.state.status === 'running') { return; }
      if (message.type === 'edit') { workflow.clear(); return; }
      if (message.type !== 'generate' && message.type !== 'approve') { return; }
      if (message.type === 'generate' && typeof message.requirement !== 'string') { return; }
      busy = true;
      send({ type: 'busy', busy: true });
      try {
        await vscode.window.withProgress({
          location: vscode.ProgressLocation.Notification,
          title: message.type === 'generate' ? 'Generating architecture rule' : 'Approving architecture rule',
        }, async () => {
          if (message.type === 'generate') {
            const response = await workflow.generate(message.requirement as string);
            // The panel needs the interpretation, not the retrieved project documents.
            const { retrieved_context: _context, ...interpretation } = response;
            send({ type: 'proposal', response: interpretation, canApprove: workflow.canApprove });
          } else {
            const result = await workflow.approve(async conflicts => {
              send({ type: 'conflicts', conflicts });
              output.appendLine(`Approval conflicts: ${conflicts.conflicts.map(item => item.existing_rule_id).join(', ')}`);
              if (disposed) { return false; }
              const details = conflicts.conflicts.map(item => `${item.existing_rule_id}: ${item.reason}`).join('\n');
              const choice = await vscode.window.showWarningMessage(
                'This rule conflicts with approved architecture rules. Approve anyway?',
                { modal: true, detail: details }, 'Approve anyway',
              );
              return !disposed && choice === 'Approve anyway';
            });
            if (result.cancelled) { send({ type: 'cancelled', canApprove: workflow.canApprove }); }
            else {
              conformance.invalidate();
              send({ type: 'approved', approval: result.approval });
            }
          }
        });
      } catch (error) {
        if (!(error instanceof BackendApiError)) {
          output.appendLine(`Unexpected error: ${error instanceof Error ? error.stack ?? error.message : String(error)}`);
        }
        const errors = error instanceof BackendApiError ? error.validationErrors : [];
        send({ type: 'error', message: friendlyError(error), errors, canApprove: workflow.canApprove });
      } finally {
        busy = false;
        send({ type: 'busy', busy: false });
      }
    });
    panel.onDidDispose(() => {
      disposed = true;
      listener.dispose();
      unsubscribeAnalysis();
      unsubscribeSync();
      unsubscribeConformance();
      editorListener.dispose();
      configurationListener.dispose();
      client.dispose();
      ArchitecturePanel.currentPanel = undefined;
    });
    context.subscriptions.push(panel);
    panel.webview.html = ArchitecturePanel.getHtmlContent(randomBytes(18).toString('hex'));
  }

  private static getHtmlContent(nonce: string): string {
    return `
      <!DOCTYPE html>
      <html lang="en">
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-${nonce}' https://cdn.jsdelivr.net; font-src https://cdn.jsdelivr.net; script-src 'nonce-${nonce}';">
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@vscode/codicons/dist/codicon.css">
        <style nonce="${nonce}">${architectureStyles}</style>
      </head>
      <body>
        <header class="header">
          <div><h1>Architecture Governance</h1><p>Analyze your project. Define rules. Review conformance.</p></div>
          <div id="backend-status" class="backend-status" role="status" aria-live="polite">AI Backend: Configuration pending</div>
        </header>
        <main>
        ${analysisFormHtml}
        ${ruleFormHtml}
        ${conformanceFormHtml}
        </main>
        <script nonce="${nonce}">${ruleWebviewScript}</script>
      </body>
      </html>
    `;
  }
}
