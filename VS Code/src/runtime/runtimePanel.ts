import * as vscode from 'vscode';

export class RuntimePanel {
  private static currentPanel: vscode.WebviewPanel | undefined;

  public static show(context: vscode.ExtensionContext) {
    if (RuntimePanel.currentPanel) {
      RuntimePanel.currentPanel.reveal(vscode.ViewColumn.Beside);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      'runtimePanel',
      'Runtime Details',
      vscode.ViewColumn.Beside,
      { enableScripts: true, retainContextWhenHidden: true }
    );

    RuntimePanel.currentPanel = panel;
    panel.onDidDispose(() => {
      RuntimePanel.currentPanel = undefined;
    });

    panel.webview.html = RuntimePanel.getHtmlContent();
  }

  private static getHtmlContent(): string {
    return `
      <!DOCTYPE html>
      <html lang="en">
      <head>
        <meta charset="UTF-8">
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@vscode/codicons/dist/codicon.css">
        <style>
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
            background-color: var(--vscode-inputValidation-errorBackground);
            color: var(--vscode-inputValidation-errorForeground);
            border: 1px solid var(--vscode-inputValidation-errorBorder);
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
        </style>
      </head>
      <body>
        <div class="header">
          <i class="codicon codicon-bug" style="font-size: 18px; color: var(--vscode-editorError-foreground);"></i>
          <h2>Runtime Errors Breakdown</h2>
        </div>
        <div class="issue-card">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <strong>NullPointerException Risk</strong>
            <span class="tag">Critical</span>
          </div>
          <p style="font-size: 12px; margin: 0; color: var(--vscode-descriptionForeground);">
            Method parameter dereferenced without a defensive null check.
          </p>
          <div class="code-box">AuthService.java &rarr; validateToken(String token)</div>
        </div>
      </body>
      </html>
    `;
  }
}