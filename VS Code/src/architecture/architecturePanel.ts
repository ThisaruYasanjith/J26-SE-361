import * as vscode from 'vscode';
import { randomBytes } from 'node:crypto';
import { ArchitectureBackendClient, BackendApiError, DEFAULT_BACKEND_URL, friendlyError } from './backendClient';
import { isRecord } from './contracts';
import { ArchitectureRuleWorkflow } from './ruleWorkflow';
import { ruleFormHtml, ruleWebviewScript } from './architectureView';

export class ArchitecturePanel {
  private static currentPanel: vscode.WebviewPanel | undefined;

  public static show(context: vscode.ExtensionContext, output: vscode.OutputChannel) {
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
    const listener = panel.webview.onDidReceiveMessage(async (message: unknown) => {
      if (!isRecord(message) || busy || disposed) { return; }
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
            else { send({ type: 'approved', approval: result.approval }); }
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
        <style nonce="${nonce}">
          body {
            background-color: var(--vscode-editor-background);
            color: var(--vscode-editor-foreground);
            font-family: var(--vscode-font-family);
            font-size: var(--vscode-font-size);
            padding: 16px;
            margin: 0;
          }
          .header {
            display: flex;
            align-items: center;
            gap: 10px;
            border-bottom: 1px solid var(--vscode-panel-border);
            padding-bottom: 12px;
            margin-bottom: 16px;
          }
          .header h2 { margin: 0; font-size: 15px; }
          .issue-card {
            background-color: var(--vscode-editorWidget-background);
            border: 1px solid var(--vscode-widget-border, var(--vscode-panel-border));
            border-radius: 4px;
            padding: 12px;
            margin-bottom: 12px;
          }
          .tag {
            background-color: var(--vscode-badge-background);
            color: var(--vscode-badge-foreground);
            font-size: 11px;
            padding: 2px 6px;
            border-radius: 3px;
          }
          .code-box {
            background-color: var(--vscode-textCodeBlock-background);
            padding: 6px 10px;
            border-radius: 3px;
            font-family: var(--vscode-editor-font-family, monospace);
            font-size: 12px;
            margin-top: 8px;
            border: 1px solid var(--vscode-panel-border);
          }
          textarea { box-sizing: border-box; width: 100%; min-height: 85px; margin: 8px 0;
            background: var(--vscode-input-background); color: var(--vscode-input-foreground);
            border: 1px solid var(--vscode-input-border, var(--vscode-panel-border)); padding: 8px; font: inherit; }
          button { background: var(--vscode-button-background); color: var(--vscode-button-foreground);
            border: 0; padding: 7px 12px; margin: 4px 6px 4px 0; cursor: pointer; }
          button:disabled { opacity: .5; cursor: default; }
          pre, dd { white-space: pre-wrap; overflow-wrap: anywhere; }
          dt { font-weight: bold; margin-top: 8px; }
          dd { margin-left: 0; }
          #rule-status, #validation-errors, #conflicts { white-space: pre-wrap; }
          #validation-errors, #conflicts { color: var(--vscode-editorWarning-foreground); }
          .header i { font-size: 18px; color: var(--vscode-editorInfo-foreground); }
          .issue-heading { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
          .issue-card p { font-size: 12px; margin: 0; color: var(--vscode-descriptionForeground); }
        </style>
      </head>
      <body>
        <div class="header">
          <i class="codicon codicon-type-hierarchy"></i>
          <h2>Architecture Breakdown</h2>
        </div>
        ${ruleFormHtml}
        <div class="issue-card">
          <div class="issue-heading">
            <strong>Layering Violation</strong>
            <span class="tag">High</span>
          </div>
          <p>
            Controller layer directly accesses persistence repositories.
          </p>
          <div class="code-box">UserController.java &rarr; UserRepository.java</div>
        </div>
        <script nonce="${nonce}">${ruleWebviewScript}</script>
      </body>
      </html>
    `;
  }
}
