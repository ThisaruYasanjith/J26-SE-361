import * as vscode from 'vscode';
import { JavaMethodUtils } from './javaMethodUtils';

export class BehaviouralPanel {
  private static currentPanel: vscode.WebviewPanel | undefined;
  private static trackedDocUri: vscode.Uri | undefined;
  private static trackedMethodName: string | undefined;

  public static show(context: vscode.ExtensionContext) {
    if (BehaviouralPanel.currentPanel) {
      BehaviouralPanel.currentPanel.reveal(vscode.ViewColumn.Beside);
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

    panel.webview.html = BehaviouralPanel.getHtmlContent();

    // Handle messages from the webview
    panel.webview.onDidReceiveMessage(async (message) => {
      switch (message.command) {
        case 'checkHealth': {
          const health = await BehaviouralPanel.checkServiceHealth();
          panel.webview.postMessage({ command: 'healthStatus', data: health });
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
      }
    });
  }

  public static captureFromActiveEditor(context: vscode.ExtensionContext, target: 'v1' | 'v2'): void {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage('No active editor. Please open a Java file first.');
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
    const url = `${this.getServiceUrl()}/health`;
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(4000) });
      if (response.ok) {
        const data = await response.json();
        return { connected: true, details: data };
      }
      return { connected: false, error: `Service HTTP ${response.status}` };
    } catch (e: any) {
      return { connected: false, error: e.message || 'Connection refused' };
    }
  }

  private static async analyzeMethods(oldMethod: string, newMethod: string): Promise<any> {
    const url = `${this.getServiceUrl()}/analyze_pipeline`;
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
          .chip-added { background-color: #1e3a2f; color: #4ade80; border-color: #2e6047; }
          .chip-removed { background-color: #3d1f24; color: #f87171; border-color: #652b32; }
          .chip-retained { background-color: #1e293b; color: #94a3b8; border-color: #334155; }

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

        <div style="margin-bottom: 12px;">
          <label for="presetSelect">Load Preset Refactoring Scenario:</label>
          <select id="presetSelect" onchange="loadPreset()">
            <option value="001">Dataset #001: Files.copy -> updateStatus & deleteIfExists (DB Write Added)</option>
            <option value="003">Dataset #003: findById -> writeString & findById (File Operation Added)</option>
            <option value="004">Dataset #004: Added Null Check & IllegalArgumentException</option>
            <option value="race">Race Condition Demonstration: CacheManager.java (Thread Mutation)</option>
            <option value="custom">-- Custom Java Methods --</option>
          </select>
        </div>

        <div id="autoCaptureBanner" class="issue-card" style="display:none; background-color: rgba(74, 222, 128, 0.12); border-color: #2e6047; margin-bottom: 12px;">
          <div style="display: flex; align-items: center; justify-content: space-between;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <i class="codicon codicon-pass" style="color: #4ade80; font-size: 16px;"></i>
              <strong style="color: #4ade80;">Auto-Captured Refactored Method!</strong>
            </div>
            <button class="secondary-btn" style="padding: 2px 6px; font-size: 10px;" onclick="document.getElementById('autoCaptureBanner').style.display='none'">Dismiss</button>
          </div>
          <p id="autoCaptureText" style="font-size: 12px; margin: 4px 0 0 0; color: var(--vscode-foreground);"></p>
        </div>

        <div class="grid-2">
          <div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
              <label for="oldMethodInput" style="margin-bottom: 0;">Baseline Java Method (v1):</label>
              <button class="secondary-btn" style="padding: 2px 8px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px;" onclick="captureBaseline()" title="Capture selected Java method from active VS Code editor">
                <i class="codicon codicon-arrow-down"></i> Capture Selection
              </button>
            </div>
            <textarea id="oldMethodInput" rows="8"></textarea>
            <div id="v1Meta" style="display: none; font-size: 11px; color: var(--vscode-editorInfo-foreground); margin-top: 4px;"></div>
          </div>
          <div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
              <label for="newMethodInput" style="margin-bottom: 0;">Modified Java Method (v2):</label>
              <button class="secondary-btn" style="padding: 2px 8px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px;" onclick="captureModified()" title="Capture current Java method from active VS Code editor">
                <i class="codicon codicon-arrow-down"></i> Capture Current
              </button>
            </div>
            <textarea id="newMethodInput" rows="8"></textarea>
            <div id="v2Meta" style="display: none; font-size: 11px; color: var(--vscode-editorInfo-foreground); margin-top: 4px;"></div>
          </div>
        </div>

        <div class="btn-row">
          <button id="runBtn" class="primary-btn" onclick="runAnalysis()">
            <i class="codicon codicon-play"></i>
            <span>Analyze with Fine-Tuned CodeT5</span>
          </button>
          <button class="secondary-btn" onclick="checkHealth()">
            <i class="codicon codicon-refresh"></i> Refresh Status
          </button>
        </div>

        <div id="errorBox" class="issue-card" style="display: none; border-color: #d9534f; background-color: rgba(217, 83, 79, 0.1);">
          <strong style="color: #f87171;">Analysis Failed</strong>
          <p id="errorMsg" style="font-size: 12px; margin: 6px 0 0 0;"></p>
        </div>

        <!-- Section 2: Same-Signature Verification Results -->
        <div id="stage2Section" style="display: none; margin-bottom: 16px;">
          <div class="section-title">
            <i class="codicon codicon-verified"></i>
            2. Same-Signature Verification Results
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

        <!-- Live CodeT5 Output Section -->
        <div id="resultsSection" style="display: none;">
          <div class="section-title">
            <i class="codicon codicon-symbol-class"></i>
            Fine-Tuned CodeT5 Behavioral Categories
          </div>

          <div class="grid-2">
            <div class="issue-card">
              <strong>Baseline Categories (v1)</strong>
              <div id="oldCategories" class="chip-container"></div>
              <div class="code-box" id="oldBodyBox"></div>
            </div>
            <div class="issue-card">
              <strong>Modified Categories (v2)</strong>
              <div id="newCategories" class="chip-container"></div>
              <div class="code-box" id="newBodyBox"></div>
            </div>
          </div>

          <div class="section-title">
            <i class="codicon codicon-git-compare"></i>
            Behavioral Drift Deltas
          </div>
          <div class="issue-card">
            <div style="margin-bottom: 8px;">
              <strong>Added Categories:</strong>
              <div id="addedChips" class="chip-container"></div>
            </div>
            <div style="margin-bottom: 8px;">
              <strong>Removed Categories:</strong>
              <div id="removedChips" class="chip-container"></div>
            </div>
            <div>
              <strong>Retained Categories:</strong>
              <div id="retainedChips" class="chip-container"></div>
            </div>
          </div>

          <div class="section-title">
            <i class="codicon codicon-warning"></i>
            Detected Governance Alerts
          </div>
          <div id="governanceAlerts"></div>
        </div>

        <!-- Static Fallback Card from Original Prototype UI -->
        <div id="defaultCard" class="issue-card">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <strong>Race Condition Detected</strong>
            <span class="tag tag-high">High</span>
          </div>
          <p style="font-size: 12px; margin: 0; color: var(--vscode-descriptionForeground);">
            Shared state accessed across worker threads without synchronization lock.
          </p>
          <div class="code-box">CacheManager.java &rarr; line 78</div>
        </div>

        <script>
          const vscode = acquireVsCodeApi();

          const PRESETS = {
            "001": {
              v1: "public Object buildInventoryItemSummary(InventoryItem item, Long itemId, java.nio.file.Path path, java.nio.file.Path backupPath, String message, double amount, int quantity, boolean enabled) throws java.io.IOException {\\n    java.nio.file.Files.copy(path, backupPath, java.nio.file.StandardCopyOption.REPLACE_EXISTING);\\n    return \\\"INVENTORYITEM-\\\" + itemId;\\n}",
              v2: "public Object buildInventoryItemSummary(InventoryItem item, Long itemId, java.nio.file.Path path, java.nio.file.Path backupPath, String message, double amount, int quantity, boolean enabled) throws java.io.IOException {\\n    inventoryRepository.updateStatus(itemId, \\\"PENDING\\\");\\n    java.nio.file.Files.deleteIfExists(path);\\n    return String.valueOf(itemId);\\n}"
            },
            "003": {
              v1: "public void processAccountFile(Account account, Long accountId, java.nio.file.Path path, java.nio.file.Path backupPath, String message, double amount, int quantity, boolean enabled) throws java.io.IOException {\\n    accountRepository.findById(accountId);\\n}",
              v2: "public void processAccountFile(Account account, Long accountId, java.nio.file.Path path, java.nio.file.Path backupPath, String message, double amount, int quantity, boolean enabled) throws java.io.IOException {\\n    java.nio.file.Files.writeString(path, message);\\n    accountRepository.findById(accountId);\\n}"
            },
            "004": {
              v1: "public void checkMessageRecordRequest(MessageRecord messageRecord, Long messageId, java.nio.file.Path path, java.nio.file.Path backupPath, String message, double amount, int quantity, boolean enabled) throws java.io.IOException {\\n    logger.trace(\\\"MessageRecord operation started\\\");\\n    double averageAmount = amount / Math.max(quantity, 1);\\n}",
              v2: "public void checkMessageRecordRequest(MessageRecord messageRecord, Long messageId, java.nio.file.Path path, java.nio.file.Path backupPath, String message, double amount, int quantity, boolean enabled) throws java.io.IOException {\\n    logger.trace(\\\"MessageRecord operation started\\\");\\n    double averageAmount = amount / Math.max(quantity, 1);\\n    if (messageId == null) {\\n        throw new IllegalArgumentException(\\\"identifier is required\\\");\\n    }\\n}"
            },
            "race": {
              v1: "public void updateCache(String key, Object val) {\\n    cacheMap.put(key, val);\\n}",
              v2: "public void updateCache(String key, Object val) {\\n    // Race condition: unsynchronized state update across threads\\n    this.lastAccessTime = System.currentTimeMillis();\\n    cacheMap.put(key, val);\\n}"
            }
          };

          function loadPreset() {
            const key = document.getElementById('presetSelect').value;
            if (PRESETS[key]) {
              document.getElementById('oldMethodInput').value = PRESETS[key].v1;
              document.getElementById('newMethodInput').value = PRESETS[key].v2;
            }
          }

          function captureBaseline() {
            vscode.postMessage({ command: 'captureBaselineFromEditor' });
          }

          function captureModified() {
            vscode.postMessage({ command: 'captureModifiedFromEditor' });
          }

          function checkHealth() {
            vscode.postMessage({ command: 'checkHealth' });
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

            vscode.postMessage({
              command: 'analyze',
              oldMethod,
              newMethod
            });
          }

          function showError(msg) {
            document.getElementById('errorBox').style.display = 'block';
            document.getElementById('errorMsg').innerText = msg;
            const btn = document.getElementById('runBtn');
            btn.disabled = false;
            btn.innerHTML = '<i class="codicon codicon-play"></i> <span>Analyze with Fine-Tuned CodeT5</span>';
          }

          function renderChips(containerId, list, extraClass) {
            const container = document.getElementById(containerId);
            container.innerHTML = '';
            if (!list || list.length === 0) {
              container.innerHTML = '<span style="font-size:11px; opacity:0.6;">None</span>';
              return;
            }
            list.forEach(c => {
              const span = document.createElement('span');
              span.className = 'cat-chip ' + (extraClass || '');
              span.innerText = c;
              container.appendChild(span);
            });
          }

          // Handle incoming messages from extension
          window.addEventListener('message', event => {
            const msg = event.data;
            switch (msg.command) {
              case 'healthStatus': {
                const statusPill = document.getElementById('serviceStatus');
                const statusText = document.getElementById('statusText');
                if (msg.data && msg.data.connected) {
                  statusPill.className = 'status-pill status-online';
                  statusText.innerText = 'CodeT5 Online (' + (msg.data.details.device || 'Ready') + ')';
                } else {
                  statusPill.className = 'status-pill status-offline';
                  statusText.innerText = 'CodeT5 Offline (Port 8000)';
                }
                break;
              }
              case 'updateBaselineMethod': {
                document.getElementById('oldMethodInput').value = msg.methodCode || '';
                const meta = document.getElementById('v1Meta');
                meta.style.display = 'block';
                meta.innerText = '📍 Captured from ' + (msg.fileName || 'editor') + ': ' + (msg.signature || msg.methodName);
                break;
              }
              case 'updateModifiedMethod': {
                document.getElementById('newMethodInput').value = msg.methodCode || '';
                const meta = document.getElementById('v2Meta');
                meta.style.display = 'block';
                meta.innerText = '📍 Captured from ' + (msg.fileName || 'editor') + ': ' + (msg.signature || msg.methodName);
                break;
              }
              case 'autoCapturedRefactoredMethod': {
                document.getElementById('newMethodInput').value = msg.methodCode || '';
                const meta = document.getElementById('v2Meta');
                meta.style.display = 'block';
                meta.innerText = '📍 Auto-Captured on Save: ' + (msg.signature || msg.methodName);
                const banner = document.getElementById('autoCaptureBanner');
                const bannerText = document.getElementById('autoCaptureText');
                banner.style.display = 'block';
                bannerText.innerText = 'Refactored method "' + msg.methodName + '" in ' + msg.fileName + ' detected on Save and populated into Modified (v2). Ready to analyze!';
                break;
              }
              case 'analysisResult': {
                const btn = document.getElementById('runBtn');
                btn.disabled = false;
                btn.innerHTML = '<i class="codicon codicon-play"></i> <span>Analyze with Fine-Tuned CodeT5</span>';

                if (!msg.success) {
                  showError(msg.error);
                  return;
                }

                const data = msg.data;
                document.getElementById('defaultCard').style.display = 'none';

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

                // Render categories
                renderChips('oldCategories', data.old_method.categories, '');
                renderChips('newCategories', data.new_method.categories, '');
                document.getElementById('oldBodyBox').innerText = data.old_method.method_body;
                document.getElementById('newBodyBox').innerText = data.new_method.method_body;

                // Render comparison
                const comp = data.comparison || {};
                renderChips('addedChips', comp.added_categories, 'chip-added');
                renderChips('removedChips', comp.removed_categories, 'chip-removed');
                renderChips('retainedChips', comp.retained_categories, 'chip-retained');

                // Render dynamic alerts
                const alertsDiv = document.getElementById('governanceAlerts');
                alertsDiv.innerHTML = '';

                if (comp.drift_detected) {
                  const added = comp.added_categories || [];
                  if (added.includes('EXCEPTION_BEHAVIOR')) {
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
                  if (added.includes('DATABASE_WRITE') || added.includes('FILE_OPERATION') || added.includes('EXTERNAL_CALL')) {
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
                  if (added.includes('STATE_MUTATION')) {
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
                } else {
                  alertsDiv.innerHTML = \`
                    <div class="issue-card">
                      <div style="display:flex; justify-content:space-between; align-items:center;">
                        <strong>Behavioral Integrity Maintained</strong>
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

          // Initialize with preset 001 and check health
          loadPreset();
          checkHealth();
        </script>
      </body>
      </html>
    `;
  }
}