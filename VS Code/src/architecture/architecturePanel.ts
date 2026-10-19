import * as vscode from 'vscode';

export class ArchitecturePanel {
  private static currentPanel: vscode.WebviewPanel | undefined;

  public static show(context: vscode.ExtensionContext) {
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
    panel.onDidDispose(() => {
      ArchitecturePanel.currentPanel = undefined;
    });

    panel.webview.html = ArchitecturePanel.getHtmlContent();
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
        </style>
      </head>
      <body>
        <div class="header">
          <i class="codicon codicon-type-hierarchy" style="font-size: 18px; color: var(--vscode-editorInfo-foreground);"></i>
          <h2>Architecture Breakdown</h2>
        </div>
        <div class="issue-card">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <strong>Layering Violation</strong>
            <span class="tag">High</span>
          </div>
          <p style="font-size: 12px; margin: 0; color: var(--vscode-descriptionForeground);">
            Controller layer directly accesses persistence repositories.
          </p>
          <div class="code-box">UserController.java &rarr; UserRepository.java</div>
        </div>
      </body>
      </html>
    `;
  }
}