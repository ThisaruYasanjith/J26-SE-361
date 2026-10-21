import * as vscode from 'vscode';
import { JavaMethodUtils } from './javaMethodUtils';
function getNonce(): string {
  let text = '';
  const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  for (let i = 0; i < 32; i++) {
    text += possible.charAt(Math.floor(Math.random() * possible.length));
  }
  return text;
}

export class BehaviouralPanel {
  private static currentPanel: vscode.WebviewPanel | undefined;
  private static trackedDocUri: vscode.Uri | undefined;
  private static trackedMethodName: string | undefined;

  public static show(context: vscode.ExtensionContext) {
    if (BehaviouralPanel.currentPanel) {
      BehaviouralPanel.currentPanel.reveal(vscode.ViewColumn.Beside);
      BehaviouralPanel.currentPanel.webview.html = BehaviouralPanel.getHtmlContent(BehaviouralPanel.currentPanel.webview);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      'behaviouralPanel',
      'Behavioural Details',
      vscode.ViewColumn.Beside,
      { enableScripts: true, retainContextWhenHidden: true }
    );

    BehaviouralPanel.currentPanel = panel;

    // Document Save Listener: Auto-detects saved refactored method and updates v2 box
    const saveListener = vscode.workspace.onDidSaveTextDocument((doc) => {
      if (!BehaviouralPanel.currentPanel) {
        return;
      }
      if (!doc.fileName.endsWith('.java') && doc.languageId !== 'java') {
        return;
      }
      if (BehaviouralPanel.trackedMethodName) {
        const refactored = JavaMethodUtils.findMethodByName(doc, BehaviouralPanel.trackedMethodName);
        if (refactored) {
          BehaviouralPanel.currentPanel.webview.postMessage({
            command: 'autoCapturedRefactoredMethod',
            methodCode: refactored.fullCode,
            methodName: refactored.name,
            signature: refactored.signature,
            fileName: doc.fileName.split(/[/\\]/).pop(),
          });
          vscode.window.showInformationMessage(
            `✨ Refactored method "${refactored.name}" auto-captured on Save into Modified (v2)!`
          );
        }
      }
    });

    panel.onDidDispose(() => {
      saveListener.dispose();
      BehaviouralPanel.currentPanel = undefined;
    });

    // Handle messages from the webview (register BEFORE setting html so initial messages are not dropped)
    panel.webview.onDidReceiveMessage(async (message) => {
      switch (message.command) {
        case 'checkHealth': {
          const health = await BehaviouralPanel.checkServiceHealth();
          panel.webview.postMessage({ command: 'healthStatus', data: health });
          if (health.connected && health.details?.status === 'ready') {
            vscode.window.showInformationMessage(`CodeT5 Service Online (${health.details?.device?.toUpperCase() || 'Ready'})`);
          } else {
            vscode.window.showWarningMessage(`CodeT5 Service Offline: ${health.error || 'Please run inference_service.py on port 8000'}`);
          }
          break;
        }
        case 'captureBaselineFromEditor': {
          BehaviouralPanel.captureFromActiveEditor(context, 'v1');
          break;
        }
        case 'captureModifiedFromEditor': {
          BehaviouralPanel.captureFromActiveEditor(context, 'v2');
          break;
        }
        case 'analyze': {
          try {
            const data = await BehaviouralPanel.analyzeMethods(message.oldMethod, message.newMethod);
            panel.webview.postMessage({ command: 'analysisResult', success: true, data });
          } catch (error: any) {
            panel.webview.postMessage({
              command: 'analysisResult',
              success: false,
              error: error.message || String(error)
            });
          }
          break;
        }
        case 'resetState': {
          BehaviouralPanel.trackedDocUri = undefined;
          BehaviouralPanel.trackedMethodName = undefined;
          vscode.window.showInformationMessage('Behavioral Analysis panel reset.');
          break;
        }
      }
    });

    panel.webview.html = BehaviouralPanel.getHtmlContent(panel.webview);
  }

  public static captureFromActiveEditor(context: vscode.ExtensionContext, target: 'v1' | 'v2'): void {
    // When webview has focus, activeTextEditor might be undefined; fallback to visibleTextEditors
    let editor = vscode.window.activeTextEditor;
    if (!editor || (!editor.document.fileName.endsWith('.java') && editor.document.languageId !== 'java')) {
      editor = vscode.window.visibleTextEditors.find(
        (e) => e.document.fileName.endsWith('.java') || e.document.languageId === 'java'
      );
    }

    if (!editor) {
      vscode.window.showWarningMessage('No active Java editor detected. Please open a Java file beside the panel.');
      return;
    }
    const doc = editor.document;
    if (!doc.fileName.endsWith('.java') && doc.languageId !== 'java') {
      vscode.window.showWarningMessage('Active file is not a Java document.');
      return;
    }

    const method = JavaMethodUtils.extractFromSelectionOrCursor(doc, editor.selection);
    if (!method) {
      vscode.window.showWarningMessage('Could not detect a Java method at selection/cursor. Please select the method declaration or body.');
      return;
    }

    // Ensure the panel is visible
    BehaviouralPanel.show(context);

    const fileName = doc.fileName.split(/[/\\]/).pop() || 'Editor';

    if (target === 'v1') {
      BehaviouralPanel.trackedDocUri = doc.uri;
      BehaviouralPanel.trackedMethodName = method.name;
      BehaviouralPanel.currentPanel?.webview.postMessage({
        command: 'updateBaselineMethod',
        methodCode: method.fullCode,
        methodName: method.name,
        signature: method.signature,
        fileName: fileName,
      });
      vscode.window.showInformationMessage(`Baseline (v1) captured: "${method.name}". Now refactor and save file to auto-populate Modified (v2)!`);
    } else {
      BehaviouralPanel.currentPanel?.webview.postMessage({
        command: 'updateModifiedMethod',
        methodCode: method.fullCode,
        methodName: method.name,
        signature: method.signature,
        fileName: fileName,
      });
      vscode.window.showInformationMessage(`Modified (v2) captured: "${method.name}".`);
    }
  }

  private static getServiceUrl(): string {
    const config = vscode.workspace.getConfiguration('codeGovernance');
    return (config.get<string>('behaviouralServiceUrl') || 'http://localhost:8000').replace(/\/$/, '');
  }

  private static async checkServiceHealth(): Promise<{ connected: boolean; details?: any; error?: string }> {
    const primaryUrl = `${this.getServiceUrl()}/health`;
    try {
      const response = await fetch(primaryUrl, { signal: AbortSignal.timeout(4000) });
      if (response.ok) {
        const data = await response.json();
        return { connected: true, details: data };
      }
      return { connected: false, error: `Service HTTP ${response.status}` };
    } catch (e: any) {
      // Fallback for Windows localhost IPv6 vs IPv4 resolution
      if (primaryUrl.includes('localhost')) {
        try {
          const fallbackUrl = primaryUrl.replace('localhost', '127.0.0.1');
          const fallbackRes = await fetch(fallbackUrl, { signal: AbortSignal.timeout(4000) });
          if (fallbackRes.ok) {
            const data = await fallbackRes.json();
            return { connected: true, details: data };
          }
        } catch (_) {}
      }
      return { connected: false, error: e.message || 'Connection refused' };
    }
  }

  private static async analyzeMethods(oldMethod: string, newMethod: string): Promise<any> {
    const serviceUrl = this.getServiceUrl();
    const urls = [
      `${serviceUrl}/analyze_pipeline`,
      serviceUrl.includes('localhost') ? `${serviceUrl.replace('localhost', '127.0.0.1')}/analyze_pipeline` : null
    ].filter(Boolean) as string[];

    let lastError: any = null;
    for (const url of urls) {
      try {
        const response = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ old_method: oldMethod, new_method: newMethod }),
          signal: AbortSignal.timeout(60000)
        });

        if (!response.ok) {
          let errText = await response.text();
          try {
            const errJson = JSON.parse(errText);
            if (errJson.detail) {
              errText = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
            }
          } catch (_) {}
          throw new Error(`Inference service error (${response.status}): ${errText}`);
        }

        return await response.json();
      } catch (err: any) {
        lastError = err;
      }
    }

    throw lastError || new Error('Connection refused');
  }

  private static getHtmlContent(webview: vscode.Webview): string {
    const nonce = getNonce();
    return `
      <!DOCTYPE html>
      <html lang="en">
      <head>
        <meta charset="UTF-8">
        <meta http-equiv="Content-Security-Policy" content="default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; script-src * 'unsafe-inline' 'unsafe-eval' 'nonce-${nonce}'; style-src * 'unsafe-inline' https:; font-src * data: https:;">
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@vscode/codicons/dist/codicon.css">
        <style>
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
          .header h2 { margin: 0; font-size: 15px; }
          .status-pill {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            padding: 3px 8px;
            border-radius: 12px;
            background-color: var(--vscode-badge-background);
            color: var(--vscode-badge-foreground);
          }
          .status-online { background-color: #1e3a2f; color: #4ade80; border: 1px solid #2e6047; }
          .status-offline { background-color: #3d1f24; color: #f87171; border: 1px solid #652b32; }
          .status-checking { background-color: rgba(240, 173, 78, 0.2); color: #f0ad4e; border: 1px solid #f0ad4e; }
          .spin-icon { animation: spin 1s linear infinite; display: inline-block; }

          .section-title {
            font-size: 13px;
            font-weight: 600;
            margin: 16px 0 8px 0;
            color: var(--vscode-editorInfo-foreground);
            display: flex;
            align-items: center;
            gap: 6px;
          }

          .grid-2 {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-bottom: 12px;
          }

          label {
            font-size: 12px;
            font-weight: 600;
            margin-bottom: 4px;
            display: block;
            color: var(--vscode-descriptionForeground);
          }

          textarea, select {
            width: 100%;
            box-sizing: border-box;
            background-color: var(--vscode-input-background);
            color: var(--vscode-input-foreground);
            border: 1px solid var(--vscode-input-border, var(--vscode-panel-border));
            border-radius: 3px;
            padding: 8px;
            font-family: var(--vscode-editor-font-family, monospace);
            font-size: 12px;
            resize: vertical;
          }
          textarea:focus, select:focus {
            outline: 1px solid var(--vscode-focusBorder);
          }

          .btn-row {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 16px;
          }

          button.primary-btn {
            background-color: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: none;
            padding: 8px 16px;
            border-radius: 3px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 6px;
          }
          button.primary-btn:hover {
            background-color: var(--vscode-button-hoverBackground);
          }
          button.primary-btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
          }

          button.secondary-btn {
            background-color: var(--vscode-button-secondaryBackground, #3a3d41);
            color: var(--vscode-button-secondaryForeground, #ffffff);
            border: none;
            padding: 8px 12px;
            border-radius: 3px;
            font-size: 12px;
            cursor: pointer;
          }

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
          .tag-high { background-color: #d9534f; color: #fff; }
          .tag-med { background-color: #f0ad4e; color: #fff; }
          .tag-low { background-color: #5cb85c; color: #fff; }

          .code-box {
            background-color: var(--vscode-textCodeBlock-background);
            padding: 8px 10px;
            border-radius: 3px;
            font-family: var(--vscode-editor-font-family, monospace);
            font-size: 12px;
            margin-top: 8px;
            border: 1px solid var(--vscode-panel-border);
            white-space: pre-wrap;
            max-height: 200px;
            overflow-y: auto;
          }

          .chip-container {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin: 6px 0;
          }
          .cat-chip {
            font-family: var(--vscode-editor-font-family, monospace);
            font-size: 11px;
            padding: 3px 8px;
            border-radius: 3px;
            background-color: var(--vscode-editorWidget-background);
            border: 1px solid var(--vscode-panel-border);
            font-weight: 600;
          }
          .stat-card {
            background: var(--vscode-editorWidget-background);
            border: 1px solid var(--vscode-widget-border, var(--vscode-panel-border));
            border-left: 4px solid #38bdf8;
            border-radius: 4px;
            padding: 10px 12px;
          }
          .stat-card-title {
            font-size: 11px;
            color: var(--vscode-descriptionForeground);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
          }
          .stat-card-val {
            font-size: 18px;
            font-weight: 700;
            color: var(--vscode-editor-foreground);
          }
          .badge-critical { color: #fff; background-color: #d9534f; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; }
          .badge-high { color: #fff; background-color: #f0ad4e; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; }
          .badge-medium { color: #fff; background-color: #0275d8; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; }
          .badge-low { color: #fff; background-color: #5cb85c; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; }
          .badge-none { color: #fff; background-color: #6c757d; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; }
          .grid-3 {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 10px;
            margin-bottom: 12px;
          }
          @media (max-width: 600px) {
            .grid-3 { grid-template-columns: 1fr; }
            .grid-2 { grid-template-columns: 1fr; }
          }
          .cat-badge {
            display: inline-block;
            background-color: #2b3a4a;
            color: #61dafb;
            padding: 3px 8px;
            border-radius: 4px;
            margin-right: 6px;
            margin-bottom: 4px;
            font-family: var(--vscode-editor-font-family, monospace);
            font-size: 11px;
            font-weight: 600;
            border: 1px solid #3d5166;
          }
          .cat-added {
            background-color: #1e3a2f;
            color: #4ade80;
            border-color: #2e6047;
          }
          .cat-removed {
            background-color: #3d1f24;
            color: #f87171;
            border-color: #652b32;
          }
          .cat-retained {
            background-color: #1e293b;
            color: #94a3b8;
            border-color: #334155;
          }
          .method-body-expander {
            margin-top: 8px;
            border: 1px solid var(--vscode-panel-border);
            border-radius: 3px;
            background: rgba(0, 0, 0, 0.15);
          }
          .method-body-expander summary {
            padding: 6px 10px;
            font-size: 11px;
            font-weight: 600;
            cursor: pointer;
            color: var(--vscode-descriptionForeground);
            user-select: none;
          }
          .method-body-expander summary:hover {
            color: var(--vscode-foreground);
          }

          .spinner {
            display: inline-block;
            width: 14px;
            height: 14px;
            border: 2px solid rgba(255,255,255,0.3);
            border-radius: 50%;
            border-top-color: #fff;
            animation: spin 1s ease-in-out infinite;
          }
          @keyframes spin { to { transform: rotate(360deg); } }
        </style>
      </head>
      <body>
        <div class="header">
          <div class="header-left">
            <i class="codicon codicon-pulse" style="font-size: 18px; color: var(--vscode-editorInfo-foreground);"></i>
            <h2>Behavioural Analysis Breakdown</h2>
          </div>
          <div id="serviceStatus" class="status-pill status-offline">
            <i class="codicon codicon-radio-tower"></i>
            <span id="statusText">Checking CodeT5...</span>
          </div>
        </div>



        <div id="autoCaptureBanner" class="issue-card" style="display:none; background-color: rgba(74, 222, 128, 0.12); border-color: #2e6047; margin-bottom: 12px;">
          <div style="display: flex; align-items: center; justify-content: space-between;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <i class="codicon codicon-pass" style="color: #4ade80; font-size: 16px;"></i>
              <strong style="color: #4ade80;">Auto-Captured Refactored Method!</strong>
            </div>
            <button id="dismissBannerBtn" class="secondary-btn" style="padding: 2px 6px; font-size: 10px;" onclick="dismissBanner()">Dismiss</button>
          </div>
          <p id="autoCaptureText" style="font-size: 12px; margin: 4px 0 0 0; color: var(--vscode-foreground);"></p>
        </div>

        <div class="grid-2">
          <div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
              <label for="oldMethodInput" style="margin-bottom: 0;">Baseline Java Method (v1):</label>
              <button id="captureBaselineBtn" class="secondary-btn" style="padding: 2px 8px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px;" onclick="captureBaseline()" title="Capture selected Java method from active VS Code editor">
                <i class="codicon codicon-arrow-down"></i> Capture Selection
              </button>
            </div>
            <textarea id="oldMethodInput" rows="8" placeholder="Select a method in editor and click 'Capture Selection' or paste baseline code here..."></textarea>
          </div>
          <div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
              <label for="newMethodInput" style="margin-bottom: 0;">Modified Java Method (v2):</label>
              <button id="captureModifiedBtn" class="secondary-btn" style="padding: 2px 8px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px;" onclick="captureModified()" title="Capture current Java method from active VS Code editor">
                <i class="codicon codicon-arrow-down"></i> Capture Current
              </button>
            </div>
            <textarea id="newMethodInput" rows="8" placeholder="Edit and save in editor to auto-capture or paste modified code here..."></textarea>
          </div>
        </div>

        <div class="btn-row">
          <button id="runBtn" class="primary-btn" onclick="runAnalysis()">
            <i class="codicon codicon-play"></i>
            <span>Analyze Method</span>
          </button>
          <button id="refreshBtn" class="secondary-btn" onclick="checkHealth()" title="Refresh connection to CodeT5 inference service">
            <i id="refreshIcon" class="codicon codicon-refresh"></i> <span id="refreshBtnText">Refresh Status</span>
          </button>
        </div>

        <div id="errorBox" class="issue-card" style="display: none; border-color: #d9534f; background-color: rgba(217, 83, 79, 0.1);">
          <strong style="color: #f87171;">Analysis Failed</strong>
          <p id="errorMsg" style="font-size: 12px; margin: 6px 0 0 0;"></p>
        </div>

        <!-- Same-Signature Verification Results -->
        <div id="stage2Section" style="display: none; margin-bottom: 16px;">
          <div class="section-title">
            <i class="codicon codicon-verified"></i>
            Same-Signature Verification Results
          </div>
          <div id="sigVerifiedCard" class="issue-card" style="display: none; background-color: rgba(30, 58, 47, 0.35); border-color: #2e6047;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <i class="codicon codicon-check" style="color: #4ade80; font-size: 16px;"></i>
              <strong style="color: #4ade80;">Same-Signature Verified!</strong>
            </div>
            <p style="margin: 6px 0 0 0; font-size: 12px; color: var(--vscode-foreground);">
              Both methods share signature: <code id="sigVerifiedCode" style="color: #4ade80; font-family: monospace;"></code>
            </p>
          </div>
          <div id="sigMismatchCard" class="issue-card" style="display: none; background-color: rgba(61, 31, 36, 0.45); border-color: #7f1d1d;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <i class="codicon codicon-error" style="color: #f87171; font-size: 16px;"></i>
              <strong style="color: #f87171;">Signature Mismatch Detected!</strong>
            </div>
            <p id="sigMismatchSummary" style="margin: 6px 0; font-size: 12px; color: var(--vscode-foreground);"></p>
            <div id="sigMismatchesList" style="margin: 8px 0;"></div>
            <p style="margin: 8px 0 0 0; font-size: 11px; opacity: 0.8; color: var(--vscode-descriptionForeground);">
              ℹ️ Behavioral Drift Detection applies to methods with identical signatures. This change constitutes an explicit API signature change.
            </p>
          </div>
        </div>

        <!-- Fine-Tuned CodeT5 Behavioral Categories & Extracted Bodies -->
        <div id="resultsSection" style="display: none;">
          <div class="section-title">
            <i class="codicon codicon-symbol-class"></i>
            Fine-Tuned CodeT5 Behavioral Categories & Extracted Bodies
          </div>

          <div class="grid-2">
            <div class="issue-card">
              <div style="font-weight: 600; font-size: 12px; margin-bottom: 6px;">🏷️ Baseline Categories (v1)</div>
              <div id="oldCategories" class="chip-container"></div>
              <details class="method-body-expander" open>
                <summary>Extracted Baseline Method Body</summary>
                <div class="code-box" id="oldBodyBox">/* empty body */</div>
              </details>
            </div>
            <div class="issue-card">
              <div style="font-weight: 600; font-size: 12px; margin-bottom: 6px;">🏷️ Modified Categories (v2)</div>
              <div id="newCategories" class="chip-container"></div>
              <details class="method-body-expander" open>
                <summary>Extracted Modified Method Body</summary>
                <div class="code-box" id="newBodyBox">/* empty body */</div>
              </details>
            </div>
          </div>

          <div class="issue-card" style="margin-top: 8px;">
            <div style="font-weight: 600; font-size: 12px; margin-bottom: 8px;">📊 Behavioral Category Changes (v1 &rarr; v2)</div>
            <div class="grid-3">
              <div>
                <strong id="addedHeader" style="font-size: 12px; color: #4ade80;">➕ Added in v2 (0):</strong>
                <div id="addedChips" class="chip-container" style="margin-top: 4px;"></div>
              </div>
              <div>
                <strong id="removedHeader" style="font-size: 12px; color: #f87171;">➖ Removed from v1 (0):</strong>
                <div id="removedChips" class="chip-container" style="margin-top: 4px;"></div>
              </div>
              <div>
                <strong id="retainedHeader" style="font-size: 12px; color: #94a3b8;">🔁 Retained in Both (0):</strong>
                <div id="retainedChips" class="chip-container" style="margin-top: 4px;"></div>
              </div>
            </div>
          </div>

          <!-- Detected Governance Alerts (shown directly after Behavioral Category Changes) -->
          <div class="section-title" style="margin-top: 14px;">
            <i class="codicon codicon-warning"></i>
            Detected Governance Alerts
          </div>
          <div id="governanceAlerts" style="margin-bottom: 12px;"></div>

          <!-- Developer Guidance & Regression Test Generation -->
          <div class="section-title">
            <i class="codicon codicon-beaker"></i>
            Developer Guidance & Regression Test Generation
          </div>

          <div class="issue-card" style="margin-bottom: 12px; background: rgba(56, 189, 248, 0.08); border-color: #0284c7;">
            <p style="margin: 0; font-size: 12px;"><strong>Overview:</strong> <span id="guidanceOverviewText">None</span></p>
          </div>

          <!-- Method Body Behavioral Comparison Explanation -->
          <div class="issue-card" style="margin-bottom: 12px;">
            <div style="font-weight: 600; font-size: 12px; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
              <i class="codicon codicon-diff"></i> Method Body Behavioral Comparison
            </div>

            <div style="margin-bottom: 10px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <span style="font-size: 11px; opacity: 0.85; font-family: monospace; font-weight: 600;">Method Body Code Changes (v1 &rarr; v2):</span>
                <button id="copyChangesBtn" class="secondary-btn" style="padding: 2px 8px; font-size: 10px;" onclick="copyChanges()">📋 Copy Changes</button>
              </div>
              <div class="code-box" id="bodyDiffBox" style="white-space: pre; font-size: 11px; max-height: 250px; line-height: 1.5; font-family: var(--vscode-editor-font-family, monospace);">// No method body changes detected</div>
            </div>

            <div id="bodyComparisonText" style="font-size: 12px; line-height: 1.6; color: var(--vscode-foreground); white-space: pre-wrap;">No method body comparison available.</div>
          </div>

          <div class="issue-card" style="margin-bottom: 12px;">
            <div style="font-weight: 600; font-size: 12px; margin-bottom: 4px;">🔬 Technical Breakdown</div>
            <p id="techBreakdownText" style="font-size: 12px; margin: 0 0 10px 0; color: var(--vscode-foreground); white-space: pre-line;"></p>

            <div id="failureScenariosSec" style="display: none; margin-bottom: 10px;">
              <div style="font-weight: 600; font-size: 12px; margin-bottom: 4px; color: #f87171;">⚡ Divergent Runtime Scenarios (Failure Modes):</div>
              <div id="failureScenariosList" style="font-size: 12px; margin-left: 6px;"></div>
            </div>

            <div id="junitTestsSec" style="display: none; margin-bottom: 10px;">
              <div style="font-weight: 600; font-size: 12px; margin-bottom: 4px; color: #38bdf8;">🧪 Suggested JUnit Tests to Guard Against Drift:</div>
              <div id="junitTestsList"></div>
            </div>

            <div style="font-weight: 600; font-size: 12px; margin-bottom: 4px; color: #fbbf24;">💡 Developer Guidance:</div>
            <p id="devGuidanceText" style="font-size: 12px; margin: 0; color: var(--vscode-foreground); white-space: pre-line;"></p>
          </div>
        </div>

        <!-- Initial Workflow State Card -->
        <div id="initialGuidanceCard" class="issue-card" style="border-left: 4px solid var(--vscode-editorInfo-foreground); background: rgba(56, 189, 248, 0.05);">
          <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
            <i class="codicon codicon-info" style="color: var(--vscode-editorInfo-foreground); font-size: 16px;"></i>
            <strong style="color: var(--vscode-foreground);">Workflow Instructions:</strong>
          </div>
          <ol style="margin: 0; padding-left: 20px; font-size: 12px; line-height: 1.6; color: var(--vscode-descriptionForeground);">
            <li>Open your Java file in the editor and select/highlight any Java method.</li>
            <li>Click <strong>Capture Selection</strong> to populate <em>Baseline Java Method (v1)</em>.</li>
            <li>Refactor the method directly in your editor and press <kbd>Ctrl+S</kbd> to save. The modified code will automatically populate into <em>Modified Java Method (v2)</em>!</li>
            <li>Click <strong>Analyze Method</strong> to run the full 6-stage behavioral verification pipeline!</li>
          </ol>
        </div>

        <!-- Reset Button at bottom of panel -->
        <div style="margin-top: 24px; margin-bottom: 24px; text-align: center; border-top: 1px solid var(--vscode-widget-border, var(--vscode-panel-border)); padding-top: 16px;">
          <button id="resetBtn" class="secondary-btn" style="padding: 6px 18px; font-size: 12px; display: inline-flex; align-items: center; gap: 6px;" onclick="resetPanel()" title="Reset inputs, captured methods, and analysis results">
            <i class="codicon codicon-clear-all"></i> Reset
          </button>
        </div>

        <script nonce="${nonce}">
          let vscode;
          try {
            vscode = acquireVsCodeApi();
          } catch (e) {
            vscode = window._vscodeApi;
          }
          window._vscodeApi = vscode;

          function captureBaseline() {
            if (vscode) vscode.postMessage({ command: 'captureBaselineFromEditor' });
          }

          function captureModified() {
            if (vscode) vscode.postMessage({ command: 'captureModifiedFromEditor' });
          }

          function checkHealth() {
            const refreshBtn = document.getElementById('refreshBtn');
            const refreshIcon = document.getElementById('refreshIcon');
            const refreshBtnText = document.getElementById('refreshBtnText');
            if (refreshBtn) refreshBtn.disabled = true;
            if (refreshIcon) refreshIcon.className = 'codicon codicon-sync spin-icon';
            if (refreshBtnText) refreshBtnText.innerText = 'Checking...';

            const statusPill = document.getElementById('serviceStatus');
            const statusText = document.getElementById('statusText');
            if (statusPill) statusPill.className = 'status-pill status-checking';
            if (statusText) statusText.innerText = 'Checking CodeT5...';

            if (vscode) vscode.postMessage({ command: 'checkHealth' });
          }

          function resetPanel() {
            document.getElementById('oldMethodInput').value = '';
            document.getElementById('newMethodInput').value = '';

            document.getElementById('resultsSection').style.display = 'none';
            document.getElementById('stage2Section').style.display = 'none';
            document.getElementById('errorBox').style.display = 'none';
            document.getElementById('autoCaptureBanner').style.display = 'none';

            const btn = document.getElementById('runBtn');
            if (btn) {
              btn.disabled = false;
              btn.innerHTML = '<i class="codicon codicon-play"></i> <span>Analyze Method</span>';
            }

            const guidanceCard = document.getElementById('initialGuidanceCard');
            if (guidanceCard) {
              guidanceCard.style.display = 'block';
            }

            const alertsDiv = document.getElementById('governanceAlerts');
            if (alertsDiv) alertsDiv.innerHTML = '';

            const diffBox = document.getElementById('bodyDiffBox');
            if (diffBox) diffBox.innerHTML = '// No method body changes detected';

            if (vscode) vscode.postMessage({ command: 'resetState' });
          }

          function runAnalysis() {
            const oldMethod = document.getElementById('oldMethodInput').value.trim();
            const newMethod = document.getElementById('newMethodInput').value.trim();

            if (!oldMethod || !newMethod) {
              showError("Please enter both baseline and modified Java methods.");
              return;
            }

            document.getElementById('errorBox').style.display = 'none';
            const btn = document.getElementById('runBtn');
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner"></span> <span>Running CodeT5...</span>';

            if (vscode) {
              vscode.postMessage({
                command: 'analyze',
                oldMethod,
                newMethod
              });
            }
          }

          function dismissBanner() {
            const banner = document.getElementById('autoCaptureBanner');
            if (banner) banner.style.display = 'none';
          }

          function copyChanges() {
            const diffBox = document.getElementById('bodyDiffBox');
            const btn = document.getElementById('copyChangesBtn');
            if (diffBox && btn) {
              navigator.clipboard.writeText(diffBox.innerText).then(() => {
                const orig = btn.innerText;
                btn.innerText = '✅ Copied!';
                setTimeout(() => { btn.innerText = orig; }, 2000);
              });
            }
          }

          function showError(msg) {
            document.getElementById('errorBox').style.display = 'block';
            document.getElementById('errorMsg').innerText = msg;
            const btn = document.getElementById('runBtn');
            btn.disabled = false;
            btn.innerHTML = '<i class="codicon codicon-play"></i> <span>Analyze Method</span>';
          }

          function renderChips(containerId, list, extraClass) {
            const container = document.getElementById(containerId);
            container.innerHTML = '';
            if (!list || list.length === 0) {
              container.innerHTML = '<span style="font-size:11px; opacity:0.6; font-style:italic;">None detected</span>';
              return;
            }
            list.forEach(c => {
              const span = document.createElement('span');
              span.className = 'cat-badge ' + (extraClass || '');
              span.innerText = c;
              container.appendChild(span);
            });
          }

          // Expose to window for inline onclick handlers
          window.captureBaseline = captureBaseline;
          window.captureModified = captureModified;
          window.checkHealth = checkHealth;
          window.resetPanel = resetPanel;
          window.runAnalysis = runAnalysis;
          window.dismissBanner = dismissBanner;
          window.copyChanges = copyChanges;

          // Wire up event listeners
          document.getElementById('refreshBtn')?.addEventListener('click', checkHealth);
          document.getElementById('runBtn')?.addEventListener('click', runAnalysis);
          document.getElementById('captureBaselineBtn')?.addEventListener('click', captureBaseline);
          document.getElementById('captureModifiedBtn')?.addEventListener('click', captureModified);
          document.getElementById('resetBtn')?.addEventListener('click', resetPanel);
          document.getElementById('dismissBannerBtn')?.addEventListener('click', dismissBanner);
          document.getElementById('copyChangesBtn')?.addEventListener('click', copyChanges);

          // Delegated event listener for copying test cases
          document.addEventListener('click', (event) => {
            const target = event.target;
            if (target && target.classList && target.classList.contains('copy-test-btn')) {
              const container = target.closest('div').parentElement;
              const codeBox = container ? container.querySelector('.code-box') : null;
              if (codeBox) {
                navigator.clipboard.writeText(codeBox.innerText).then(() => {
                  const orig = target.innerText;
                  target.innerText = '✅ Copied!';
                  setTimeout(() => { target.innerText = orig; }, 2000);
                });
              }
            }
          });

          // Handle incoming messages from extension
          window.addEventListener('message', event => {
            const msg = event.data;
            switch (msg.command) {
              case 'healthStatus': {
                const refreshBtn = document.getElementById('refreshBtn');
                const refreshIcon = document.getElementById('refreshIcon');
                const refreshBtnText = document.getElementById('refreshBtnText');
                if (refreshBtn) refreshBtn.disabled = false;
                if (refreshIcon) refreshIcon.className = 'codicon codicon-refresh';
                if (refreshBtnText) {
                  refreshBtnText.innerText = 'Refreshed!';
                  setTimeout(() => {
                    const btnTxt = document.getElementById('refreshBtnText');
                    if (btnTxt) btnTxt.innerText = 'Refresh Status';
                  }, 1500);
                }

                const statusPill = document.getElementById('serviceStatus');
                const statusText = document.getElementById('statusText');
                if (msg.data && msg.data.connected && msg.data.details && msg.data.details.status === 'ready') {
                  statusPill.className = 'status-pill status-online';
                  const dev = msg.data.details.device ? msg.data.details.device.toUpperCase() : 'Ready';
                  statusText.innerText = 'CodeT5 Online (' + dev + ')';
                } else if (msg.data && msg.data.connected && msg.data.details && msg.data.details.status === 'error') {
                  statusPill.className = 'status-pill status-offline';
                  statusText.innerText = 'CodeT5 Error: ' + (msg.data.details.error || 'Model error');
                } else {
                  statusPill.className = 'status-pill status-offline';
                  statusText.innerText = 'CodeT5 Offline (Port 8000)';
                }
                break;
              }
              case 'updateBaselineMethod': {
                document.getElementById('oldMethodInput').value = msg.methodCode || '';
                break;
              }
              case 'updateModifiedMethod': {
                document.getElementById('newMethodInput').value = msg.methodCode || '';
                break;
              }
              case 'autoCapturedRefactoredMethod': {
                document.getElementById('newMethodInput').value = msg.methodCode || '';
                const banner = document.getElementById('autoCaptureBanner');
                const bannerText = document.getElementById('autoCaptureText');
                banner.style.display = 'block';
                bannerText.innerText = 'Refactored method "' + msg.methodName + '" in ' + msg.fileName + ' detected on Save and populated into Modified (v2). Ready to analyze!';
                break;
              }
              case 'analysisResult': {
                const btn = document.getElementById('runBtn');
                btn.disabled = false;
                btn.innerHTML = '<i class="codicon codicon-play"></i> <span>Analyze Method</span>';

                if (!msg.success) {
                  showError(msg.error);
                  return;
                }

                const data = msg.data;
                // Hide initial workflow guidance card on first analysis
                const guidanceCard = document.getElementById('initialGuidanceCard');
                if (guidanceCard) guidanceCard.style.display = 'none';

                // Render Stage 2: Same-Signature Verification
                const sig = data.stage2_signature;
                if (sig) {
                  document.getElementById('stage2Section').style.display = 'block';
                  if (sig.is_same_signature) {
                    document.getElementById('sigVerifiedCard').style.display = 'block';
                    document.getElementById('sigMismatchCard').style.display = 'none';
                    document.getElementById('sigVerifiedCode').innerText = sig.signature_str || 'Identical signature verified';
                  } else {
                    document.getElementById('sigVerifiedCard').style.display = 'none';
                    document.getElementById('sigMismatchCard').style.display = 'block';
                    document.getElementById('sigMismatchSummary').innerText = sig.summary || 'Method signatures differ between baseline and modified versions.';
                    const list = document.getElementById('sigMismatchesList');
                    list.innerHTML = '';
                    (sig.mismatches || []).forEach(m => {
                      list.innerHTML += \`<div style="font-size:12px; margin-bottom:4px; padding:4px 8px; background:rgba(0,0,0,0.2); border-radius:3px;">
                        <strong>\${m.component}:</strong> Baseline <code>\${m.baseline_value}</code> vs Modified <code>\${m.modified_value}</code> (\${m.description})
                      </div>\`;
                    });
                    if (data.status === 'signature_mismatch') {
                      document.getElementById('resultsSection').style.display = 'none';
                      return;
                    }
                  }
                }

                document.getElementById('resultsSection').style.display = 'block';

                // Render Stage 3: Categories & Extracted Bodies
                const s3 = data.stage3_categories || {
                  old_method: data.old_method || { categories: [], method_body: '/* empty body */' },
                  new_method: data.new_method || { categories: [], method_body: '/* empty body */' },
                  added_categories: data.comparison?.added_categories || [],
                  removed_categories: data.comparison?.removed_categories || [],
                  retained_categories: data.comparison?.retained_categories || []
                };

                renderChips('oldCategories', s3.old_method.categories, '');
                renderChips('newCategories', s3.new_method.categories, '');
                document.getElementById('oldBodyBox').innerText = s3.old_method.method_body || '/* empty body */';
                document.getElementById('newBodyBox').innerText = s3.new_method.method_body || '/* empty body */';

                // Render Category Changes
                const addedCats = s3.added_categories || [];
                const removedCats = s3.removed_categories || [];
                const retainedCats = s3.retained_categories || [];

                document.getElementById('addedHeader').innerText = '➕ Added in v2 (' + addedCats.length + '):';
                document.getElementById('removedHeader').innerText = '➖ Removed from v1 (' + removedCats.length + '):';
                document.getElementById('retainedHeader').innerText = '🔁 Retained in Both (' + retainedCats.length + '):';

                renderChips('addedChips', addedCats, 'cat-added');
                renderChips('removedChips', removedCats, 'cat-removed');
                renderChips('retainedChips', retainedCats, 'cat-retained');

                // Render Stage 4: Developer Guidance & AI Method Body Behavioral Comparison
                const s6 = data.stage6_guidance || data.stage4_guidance;
                if (s6) {
                  const overviewEl = document.getElementById('guidanceOverviewText');
                  if (overviewEl) {
                    overviewEl.innerText = s6.overview || 'Analysis complete.';
                  }

                  const bodyCompText = document.getElementById('bodyComparisonText');
                  if (bodyCompText) {
                    bodyCompText.innerText = s6.body_comparison_explanation || 'No statement-level divergence detected between baseline and modified method bodies.';
                  }

                  // Render Code Changes in Method Body Diff Box
                  const diffBox = document.getElementById('bodyDiffBox');
                  if (diffBox) {
                    let diffText = s6.code_diff;
                    const nl = String.fromCharCode(10);
                    if (!diffText) {
                      const oldLines = (s3.old_method?.method_body || '').split(nl).map(l => l.trim()).filter(l => l && !l.startsWith('//'));
                      const newLines = (s3.new_method?.method_body || '').split(nl).map(l => l.trim()).filter(l => l && !l.startsWith('//'));
                      const removed = oldLines.filter(l => !newLines.includes(l));
                      const added = newLines.filter(l => !oldLines.includes(l));
                      if (removed.length === 0 && added.length === 0) {
                        diffText = '// Method bodies are identical. No statements added or removed.';
                      } else {
                        const dLines = [];
                        removed.forEach(l => dLines.push('- ' + l));
                        added.forEach(l => dLines.push('+ ' + l));
                        diffText = dLines.join(nl);
                      }
                    }

                    const lines = (diffText || '').split(nl);
                    diffBox.innerHTML = lines.map(line => {
                      const escaped = line.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                      if (line.startsWith('+')) {
                        return '<div style="color: #4ade80; background: rgba(74, 222, 128, 0.08); padding: 1px 4px; border-radius: 2px;">' + escaped + '</div>';
                      } else if (line.startsWith('-')) {
                        return '<div style="color: #f87171; background: rgba(248, 113, 113, 0.08); padding: 1px 4px; border-radius: 2px;">' + escaped + '</div>';
                      } else {
                        return '<div style="opacity: 0.7; padding: 1px 4px;">' + escaped + '</div>';
                      }
                    }).join('');
                  }

                  const techEl = document.getElementById('techBreakdownText');
                  if (techEl) {
                    techEl.innerText = s6.detailed_drift_breakdown || 'No technical divergence breakdown available.';
                  }

                  const failSec = document.getElementById('failureScenariosSec');
                  const failList = document.getElementById('failureScenariosList');
                  if (s6.failure_scenarios && s6.failure_scenarios.length > 0) {
                    failSec.style.display = 'block';
                    failList.innerHTML = s6.failure_scenarios.map(s => \`<div style="margin-bottom: 3px;">• \${s}</div>\`).join('');
                  } else {
                    failSec.style.display = 'none';
                  }

                  const junitSec = document.getElementById('junitTestsSec');
                  const junitList = document.getElementById('junitTestsList');
                  if (s6.recommended_unit_tests && s6.recommended_unit_tests.length > 0) {
                    junitSec.style.display = 'block';
                    junitList.innerHTML = '';
                    s6.recommended_unit_tests.forEach((t, idx) => {
                      const escaped = t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                      junitList.innerHTML += \`
                        <div style="margin-bottom: 8px;">
                          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;">
                            <span style="font-size: 11px; opacity: 0.8; font-family: monospace;">Test #\${idx + 1} (JUnit 5):</span>
                            <button class="secondary-btn copy-test-btn" style="padding: 2px 8px; font-size: 10px;">📋 Copy Test</button>
                          </div>
                          <div class="code-box" style="white-space: pre; font-size: 11px; max-height: 250px;">\${escaped}</div>
                        </div>
                      \`;
                    });
                  } else {
                    junitSec.style.display = 'none';
                  }

                  document.getElementById('devGuidanceText').innerText = s6.developer_guidance || 'No specific developer guidance.';
                }

                // Render dynamic governance alerts (derived from stage 3 & 4 data)
                const alertsDiv = document.getElementById('governanceAlerts');
                alertsDiv.innerHTML = '';

                const driftDetected = (data.stage4_drift && data.stage4_drift.drift_detected) ||
                                      (s3.added_categories && s3.added_categories.length > 0);
                const addedCatsForAlerts = s3.added_categories || [];

                if (driftDetected && addedCatsForAlerts.length > 0) {
                  if (addedCatsForAlerts.includes('EXCEPTION_BEHAVIOR')) {
                    alertsDiv.innerHTML += \`
                      <div class="issue-card">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                          <strong>Unannounced Runtime Exception Injection</strong>
                          <span class="tag tag-high">High</span>
                        </div>
                        <p style="font-size:12px; margin:4px 0; color:var(--vscode-descriptionForeground);">
                          Modified implementation introduces exception behavior violating caller assumptions.
                        </p>
                      </div>
                    \`;
                  }
                  if (addedCatsForAlerts.includes('DATABASE_WRITE') || addedCatsForAlerts.includes('FILE_OPERATION') || addedCatsForAlerts.includes('EXTERNAL_CALL')) {
                    alertsDiv.innerHTML += \`
                      <div class="issue-card">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                          <strong>Unannounced External Side Effect</strong>
                          <span class="tag tag-med">Medium</span>
                        </div>
                        <p style="font-size:12px; margin:4px 0; color:var(--vscode-descriptionForeground);">
                          Method introduces side-effects (I/O, database writes, or remote calls) absent in baseline version.
                        </p>
                      </div>
                    \`;
                  }
                  if (addedCatsForAlerts.includes('STATE_MUTATION')) {
                    alertsDiv.innerHTML += \`
                      <div class="issue-card">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                          <strong>State Mutation Detected</strong>
                          <span class="tag tag-med">Medium</span>
                        </div>
                        <p style="font-size:12px; margin:4px 0; color:var(--vscode-descriptionForeground);">
                          Object state mutated without synchronization or announced contract change.
                        </p>
                      </div>
                    \`;
                  }
                  if (alertsDiv.innerHTML === '') {
                    // Drift detected but no specific category alert
                    alertsDiv.innerHTML = \`
                      <div class="issue-card" style="border-color: #f0ad4e; background: rgba(240,173,78,0.1);">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                          <strong>Behavioral Drift Detected</strong>
                          <span class="tag tag-med">Warning</span>
                        </div>
                        <p style="font-size:12px; margin:4px 0; color:var(--vscode-descriptionForeground);">
                          Behavioral categories differ between baseline and modified versions. Review added/removed categories above.
                        </p>
                      </div>
                    \`;
                  }
                } else {
                  alertsDiv.innerHTML = \`
                    <div class="issue-card" style="border-color: #2e6047; background: rgba(74,222,128,0.06);">
                      <div style="display:flex; justify-content:space-between; align-items:center;">
                        <strong style="color: #4ade80;">✅ Behavioral Integrity Maintained</strong>
                        <span class="tag tag-low">Passed</span>
                      </div>
                      <p style="font-size:12px; margin:4px 0; color:var(--vscode-descriptionForeground);">
                        No behavioral divergence detected. All behavioral categories match baseline.
                      </p>
                    </div>
                  \`;
                }

                break;
              }
            }
          });

          // Check service health on load
          checkHealth();
        </script>
      </body>
      </html>
    `;
  }
}