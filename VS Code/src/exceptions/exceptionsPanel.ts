import * as vscode from 'vscode';
import * as path from 'path';

export interface DefectItem {
  id: string;
  category: string;
  title: string;
  severity: 'Critical' | 'High' | 'Warning' | 'Medium' | 'Low' | 'Clean';
  description: string;
  recommendation: string;
  className: string;
  methodName: string;
  tryStartLine: number;
  tryEndLine: number;
  methodStartLine: number;
  methodEndLine: number;
  confidence: number;
}

export interface AnalysisResponse {
  status: 'success' | 'error';
  filePath?: string;
  totalAnalyzed?: number;
  cleanCount?: number;
  defectCount?: number;
  defects?: DefectItem[];
  message?: string;
}

export class ExceptionsPanel {
  private static currentPanel: vscode.WebviewPanel | undefined;
  private static backendUrl = 'http://127.0.0.1:8000';

  public static show(context: vscode.ExtensionContext) {
    if (ExceptionsPanel.currentPanel) {
      ExceptionsPanel.currentPanel.reveal(vscode.ViewColumn.Beside);
      ExceptionsPanel.analyzeActiveEditor();
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      'exceptionsPanel',
      'Exceptions Details',
      vscode.ViewColumn.Beside,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
      }
    );

    ExceptionsPanel.currentPanel = panel;

    panel.onDidDispose(() => {
      ExceptionsPanel.currentPanel = undefined;
    });

    // Handle messages sent from the Webview
    panel.webview.onDidReceiveMessage(async (message) => {
      switch (message.command) {
        case 'analyze':
          await ExceptionsPanel.analyzeActiveEditor();
          break;
        case 'jumpToLine':
          await ExceptionsPanel.jumpToCodeLine(
            message.filePath,
            message.startLine,
            message.endLine
          );
          break;
        case 'openSettings':
          vscode.commands.executeCommand('workbench.action.openSettings', 'exceptions');
          break;
      }
    });

    panel.webview.html = ExceptionsPanel.getHtmlContent();

    // Trigger initial analysis when panel opens
    setTimeout(() => {
      ExceptionsPanel.analyzeActiveEditor();
    }, 250);
  }

  /**
   * Analyzes the currently open file in VS Code if it is a Java file.
   */
  public static async analyzeActiveEditor() {
    if (!ExceptionsPanel.currentPanel) {
      return;
    }

    const panel = ExceptionsPanel.currentPanel;
    const editor = vscode.window.activeTextEditor;

    if (!editor) {
      panel.webview.postMessage({
        type: 'state',
        state: 'no_editor',
        message: 'No open file detected. Open a Java file to analyze exception handling defects.',
      });
      return;
    }

    const document = editor.document;
    const fileName = path.basename(document.fileName);
    const isJava = document.languageId === 'java' || fileName.endsWith('.java');

    if (!isJava) {
      panel.webview.postMessage({
        type: 'state',
        state: 'not_java',
        fileName,
        message: `Current file "${fileName}" is not a Java source file (.java).`,
      });
      return;
    }

    const code = document.getText();
    const filePath = document.fileName;

    // Send loading state to webview
    panel.webview.postMessage({
      type: 'state',
      state: 'loading',
      fileName,
      filePath,
    });

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 45000);

      const response = await fetch(`${ExceptionsPanel.backendUrl}/analyze`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          code,
          filePath,
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Server returned HTTP ${response.status}: ${errorText}`);
      }

      const result = (await response.json()) as AnalysisResponse;

      if (result.status === 'error') {
        panel.webview.postMessage({
          type: 'state',
          state: 'error',
          fileName,
          message: result.message || 'An error occurred during defect analysis.',
        });
        return;
      }

      panel.webview.postMessage({
        type: 'state',
        state: 'results',
        fileName,
        filePath,
        result,
      });
    } catch (error: any) {
      const isConnectionError =
        error.name === 'AbortError' ||
        error.code === 'ECONNREFUSED' ||
        (error.message && (
          error.message.includes('fetch failed') ||
          error.message.includes('connect') ||
          error.message.includes('ECONNREFUSED')
        ));

      panel.webview.postMessage({
        type: 'state',
        state: 'backend_offline',
        fileName,
        isConnectionError,
        message: error.message || 'Unable to connect to model microservice.',
      });
    }
  }

  /**
   * Navigates the editor to the designated line range and highlights it.
   */
  private static async jumpToCodeLine(
    targetFilePath: string | undefined,
    startLine: number,
    endLine: number
  ) {
    try {
      let document: vscode.TextDocument;
      if (targetFilePath && targetFilePath !== '<unknown>') {
        document = await vscode.workspace.openTextDocument(targetFilePath);
      } else if (vscode.window.activeTextEditor) {
        document = vscode.window.activeTextEditor.document;
      } else {
        return;
      }

      const editor = await vscode.window.showTextDocument(document, {
        viewColumn: vscode.ViewColumn.One,
        preserveFocus: false,
      });

      const actualStart = Math.max(0, startLine - 1);
      const actualEnd = Math.max(actualStart, endLine - 1);

      const range = new vscode.Range(
        new vscode.Position(actualStart, 0),
        new vscode.Position(actualEnd, 1000)
      );

      editor.selection = new vscode.Selection(range.start, range.end);
      editor.revealRange(range, vscode.TextEditorRevealType.InCenter);
    } catch (err: any) {
      vscode.window.showErrorMessage(`Failed to navigate to code: ${err.message}`);
    }
  }

  private static getHtmlContent(): string {
    return `
      <!DOCTYPE html>
      <html lang="en">
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@vscode/codicons/dist/codicon.css">
        <style>
          :root {
            --badge-critical-bg: #8c1d18;
            --badge-critical-fg: #ffffff;
            --badge-warning-bg: #855300;
            --badge-warning-fg: #ffffff;
            --badge-high-bg: #9c3f00;
            --badge-high-fg: #ffffff;
            --badge-medium-bg: #1e4f8a;
            --badge-medium-fg: #ffffff;
            --badge-low-bg: #3a3d41;
            --badge-low-fg: #cccccc;
            --badge-clean-bg: #1b6329;
            --badge-clean-fg: #ffffff;
          }
          body {
            background-color: var(--vscode-editor-background);
            color: var(--vscode-editor-foreground);
            font-family: var(--vscode-font-family);
            font-size: var(--vscode-font-size);
            padding: 16px;
            margin: 0;
            box-sizing: border-box;
          }
          .header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid var(--vscode-panel-border);
            padding-bottom: 12px;
            margin-bottom: 16px;
          }
          .header-left {
            display: flex;
            align-items: center;
            gap: 10px;
          }
          .header h2 {
            margin: 0;
            font-size: 15px;
            font-weight: 600;
          }
          .btn {
            background-color: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: none;
            border-radius: 3px;
            padding: 6px 12px;
            font-size: 12px;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: background 0.15s ease;
          }
          .btn:hover {
            background-color: var(--vscode-button-hoverBackground);
          }
          .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
          }
          .file-indicator {
            font-size: 12px;
            color: var(--vscode-descriptionForeground);
            margin-bottom: 14px;
            display: flex;
            align-items: center;
            gap: 6px;
          }
          .issue-card {
            background-color: var(--vscode-editorWidget-background);
            border: 1px solid var(--vscode-widget-border, var(--vscode-panel-border));
            border-radius: 6px;
            padding: 14px;
            margin-bottom: 14px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
            transition: transform 0.1s ease, border-color 0.15s ease;
          }
          .issue-card:hover {
            border-color: var(--vscode-focusBorder);
          }
          .card-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
            gap: 8px;
          }
          .card-title {
            font-weight: 600;
            font-size: 13.5px;
            display: flex;
            align-items: center;
            gap: 6px;
          }
          .tag-group {
            display: flex;
            align-items: center;
            gap: 6px;
          }
          .tag {
            font-size: 11px;
            font-weight: 500;
            padding: 2px 7px;
            border-radius: 3px;
            letter-spacing: 0.3px;
            text-transform: uppercase;
          }
          .tag-critical {
            background-color: var(--badge-critical-bg);
            color: var(--badge-critical-fg);
          }
          .tag-high {
            background-color: var(--badge-high-bg);
            color: var(--badge-high-fg);
          }
          .tag-warning {
            background-color: var(--badge-warning-bg);
            color: var(--badge-warning-fg);
          }
          .tag-medium {
            background-color: var(--badge-medium-bg);
            color: var(--badge-medium-fg);
          }
          .tag-low {
            background-color: var(--badge-low-bg);
            color: var(--badge-low-fg);
          }
          .tag-confidence {
            background-color: var(--vscode-badge-background);
            color: var(--vscode-badge-foreground);
            font-size: 11px;
            padding: 2px 6px;
            border-radius: 3px;
          }
          .desc {
            font-size: 12.5px;
            line-height: 1.45;
            margin: 0 0 8px 0;
            color: var(--vscode-foreground);
          }
          .rec-box {
            font-size: 12px;
            background: rgba(255, 255, 255, 0.03);
            border-left: 3px solid var(--vscode-editorInfo-foreground, #007acc);
            padding: 6px 10px;
            margin-bottom: 10px;
            border-radius: 0 3px 3px 0;
            color: var(--vscode-descriptionForeground);
          }
          .rec-box strong {
            color: var(--vscode-foreground);
          }
          .code-box {
            background-color: var(--vscode-textCodeBlock-background);
            padding: 8px 12px;
            border-radius: 4px;
            font-family: var(--vscode-editor-font-family, monospace);
            font-size: 12px;
            margin-top: 8px;
            border: 1px solid var(--vscode-panel-border);
            display: flex;
            align-items: center;
            justify-content: space-between;
            cursor: pointer;
            user-select: none;
            transition: background 0.15s ease, border-color 0.15s ease;
          }
          .code-box:hover {
            background-color: var(--vscode-list-hoverBackground);
            border-color: var(--vscode-focusBorder);
          }
          .code-box-label {
            display: flex;
            align-items: center;
            gap: 8px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
          }
          .jump-hint {
            font-size: 11px;
            color: var(--vscode-textLink-foreground);
            display: flex;
            align-items: center;
            gap: 4px;
          }
          /* Notice Boxes */
          .notice-box {
            background-color: var(--vscode-editorWidget-background);
            border: 1px solid var(--vscode-panel-border);
            border-radius: 6px;
            padding: 24px;
            text-align: center;
            margin-top: 20px;
          }
          .notice-box i {
            font-size: 32px;
            margin-bottom: 12px;
            display: inline-block;
          }
          .notice-box h3 {
            margin: 0 0 8px 0;
            font-size: 15px;
          }
          .notice-box p {
            font-size: 12.5px;
            color: var(--vscode-descriptionForeground);
            margin: 0 0 16px 0;
            line-height: 1.5;
          }
          .code-cmd {
            display: inline-block;
            background: var(--vscode-textCodeBlock-background);
            border: 1px solid var(--vscode-panel-border);
            padding: 4px 10px;
            border-radius: 4px;
            font-family: monospace;
            font-size: 12px;
            margin-top: 6px;
          }
          /* Spinner */
          .spinner {
            border: 3px solid rgba(255, 255, 255, 0.1);
            border-top: 3px solid var(--vscode-progressBar-background, #007acc);
            border-radius: 50%;
            width: 28px;
            height: 28px;
            animation: spin 0.8s linear infinite;
            margin: 0 auto 14px auto;
          }
          @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
          }
          .summary-bar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: var(--vscode-badge-background);
            color: var(--vscode-badge-foreground);
            padding: 8px 12px;
            border-radius: 4px;
            font-size: 12px;
            margin-bottom: 14px;
          }
        </style>
      </head>
      <body>
        <div class="header">
          <div class="header-left">
            <i class="codicon codicon-bug" style="font-size: 19px; color: var(--vscode-editorError-foreground);"></i>
            <h2>Exceptions Breakdown</h2>
          </div>
          <button id="refresh-btn" class="btn" title="Analyze open Java file">
            <i class="codicon codicon-refresh"></i>
            <span>Analyze File</span>
          </button>
        </div>

        <div id="file-info" class="file-indicator">
          <i class="codicon codicon-file-code"></i>
          <span id="file-name-text">Checking active file...</span>
        </div>

        <div id="content-container">
          <!-- Dynamic states will be rendered here -->
          <div class="notice-box">
            <div class="spinner"></div>
            <h3>Connecting to Exception Detector...</h3>
            <p>Evaluating active file with ablation dual-stream model.</p>
          </div>
        </div>

        <script>
          const vscode = acquireVsCodeApi();
          const container = document.getElementById('content-container');
          const fileNameText = document.getElementById('file-name-text');
          const refreshBtn = document.getElementById('refresh-btn');

          refreshBtn.addEventListener('click', () => {
            refreshBtn.disabled = true;
            vscode.postMessage({ command: 'analyze' });
          });

          window.addEventListener('message', (event) => {
            const msg = event.data;
            refreshBtn.disabled = false;

            if (msg.type === 'state') {
              renderState(msg);
            }
          });

          function renderState(msg) {
            if (msg.fileName) {
              fileNameText.textContent = msg.fileName;
            }

            switch (msg.state) {
              case 'loading':
                container.innerHTML = \`
                  <div class="notice-box">
                    <div class="spinner"></div>
                    <h3>Analyzing Exception Constructs...</h3>
                    <p>Running GraphCodeBERT semantic stream + Tree-Sitter AST structural stream on <strong>\${escapeHtml(msg.fileName || 'file')}</strong>.</p>
                  </div>
                \`;
                break;

              case 'no_editor':
                fileNameText.textContent = 'No file open';
                container.innerHTML = \`
                  <div class="notice-box">
                    <i class="codicon codicon-info" style="color: var(--vscode-editorInfo-foreground);"></i>
                    <h3>No Active Editor</h3>
                    <p>\${escapeHtml(msg.message)}</p>
                    <button class="btn" onclick="triggerAnalyze()">
                      <i class="codicon codicon-refresh"></i> Check Active File
                    </button>
                  </div>
                \`;
                break;

              case 'not_java':
                container.innerHTML = \`
                  <div class="notice-box">
                    <i class="codicon codicon-warning" style="color: var(--vscode-editorWarning-foreground);"></i>
                    <h3>Non-Java File Selected</h3>
                    <p>\${escapeHtml(msg.message)}</p>
                    <p style="font-size: 11.5px;">This model is specialized in Java exception handling defects.</p>
                  </div>
                \`;
                break;

              case 'backend_offline':
                container.innerHTML = \`
                  <div class="notice-box" style="border-color: var(--vscode-inputValidation-errorBorder);">
                    <i class="codicon codicon-plug" style="color: var(--vscode-editorError-foreground);"></i>
                    <h3 style="color: var(--vscode-editorError-foreground);">Backend Model Offline</h3>
                    <p>The exception detection service is not reachable at <strong>http://127.0.0.1:8000</strong>.</p>
                    <p>Start the microservice by running:</p>
                    <div><span class="code-cmd">python serve.py</span> (in Exceptions directory)</div>
                    <div style="margin-top: 16px;">
                      <button class="btn" onclick="triggerAnalyze()">
                        <i class="codicon codicon-refresh"></i> Retry Connection
                      </button>
                    </div>
                  </div>
                \`;
                break;

              case 'results':
                renderResults(msg.result, msg.fileName, msg.filePath);
                break;

              case 'error':
              default:
                container.innerHTML = \`
                  <div class="notice-box">
                    <i class="codicon codicon-error" style="color: var(--vscode-editorError-foreground);"></i>
                    <h3>Analysis Error</h3>
                    <p>\${escapeHtml(msg.message || 'An unexpected error occurred.')}</p>
                    <button class="btn" onclick="triggerAnalyze()">
                      <i class="codicon codicon-refresh"></i> Try Again
                    </button>
                  </div>
                \`;
                break;
            }
          }

          function renderResults(result, fileName, filePath) {
            if (!result || !result.defects || result.defects.length === 0) {
              const total = result.totalAnalyzed || 0;
              container.innerHTML = \`
                <div class="notice-box" style="border-color: var(--vscode-testing-iconPassed, #4ec9b0);">
                  <i class="codicon codicon-check-all" style="color: var(--vscode-testing-iconPassed, #4ec9b0);"></i>
                  <h3>No Exception Defects Detected</h3>
                  <p>\${
                    total > 0
                      ? 'Analyzed ' + total + ' try-catch construct(s). All constructs follow clean exception handling patterns.'
                      : (result.message || 'No try-catch blocks were found in this file.')
                  }</p>
                  <button class="btn" onclick="triggerAnalyze()">
                    <i class="codicon codicon-refresh"></i> Re-Analyze
                  </button>
                </div>
              \`;
              return;
            }

            const defectCount = result.defects.length;
            const totalCount = result.totalAnalyzed || defectCount;

            let html = \`
              <div class="summary-bar">
                <span><strong>\${defectCount} defect\${defectCount > 1 ? 's' : ''} detected</strong> (\${totalCount} try-catch construct\${totalCount > 1 ? 's' : ''} analyzed)</span>
                <span>Model: Ablation Combined (15-class)</span>
              </div>
            \`;

            result.defects.forEach((defect) => {
              const severityClass = 'tag-' + (defect.severity || 'medium').toLowerCase();
              html += \`
                <div class="issue-card">
                  <div class="card-top">
                    <div class="card-title">
                      <i class="codicon codicon-warning" style="color: var(--vscode-editorWarning-foreground);"></i>
                      <span>\${escapeHtml(defect.title)}</span>
                    </div>
                    <div class="tag-group">
                      <span class="tag \${severityClass}">\${escapeHtml(defect.severity)}</span>
                      <span class="tag-confidence">\${defect.confidence}% conf</span>
                    </div>
                  </div>

                  <p class="desc">\${escapeHtml(defect.description)}</p>

                  \${
                    defect.recommendation
                      ? \`<div class="rec-box">
                          <i class="codicon codicon-lightbulb"></i>
                          <strong>Recommendation:</strong> \${escapeHtml(defect.recommendation)}
                        </div>\`
                      : ''
                  }

                  <div class="code-box"
                       onclick="jumpTo('\${escapeHtml(filePath || '')}', \${defect.tryStartLine}, \${defect.tryEndLine})"
                       title="Click to view in editor">
                    <div class="code-box-label">
                      <i class="codicon codicon-symbol-method"></i>
                      <span>\${escapeHtml(fileName || 'File')} &rarr; \${escapeHtml(defect.className)}.\${escapeHtml(defect.methodName)}() &bull; [Lines \${defect.tryStartLine}-\${defect.tryEndLine}]</span>
                    </div>
                    <div class="jump-hint">
                      <span>Jump</span>
                      <i class="codicon codicon-arrow-right"></i>
                    </div>
                  </div>
                </div>
              \`;
            });

            container.innerHTML = html;
          }

          function jumpTo(filePath, startLine, endLine) {
            vscode.postMessage({
              command: 'jumpToLine',
              filePath,
              startLine,
              endLine,
            });
          }

          function triggerAnalyze() {
            refreshBtn.disabled = true;
            vscode.postMessage({ command: 'analyze' });
          }

          function escapeHtml(unsafe) {
            if (!unsafe) return '';
            return String(unsafe)
              .replace(/&/g, '&amp;')
              .replace(/</g, '&lt;')
              .replace(/>/g, '&gt;')
              .replace(/"/g, '&quot;')
              .replace(/'/g, '&#039;');
          }
        </script>
      </body>
      </html>
    `;
  }
}
