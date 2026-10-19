import * as vscode from "vscode";
import * as path from "path";
import * as os from "os";
import * as fs from "fs/promises";
import { spawn } from "child_process";
import { randomBytes } from "crypto";

type Finding = {
  finding_id?: string;
  concern?: string;
  scope?: string;
  symbol?: string;
  rule_id?: string;
  description?: string;
  start_line?: number;
  end_line?: number;
  source_file?: string;
  evidence?: Record<string, unknown>;
};
type Group = {
  group_id?: string;
  rank?: number;
  exceedance_score?: number;
  distinct_concern_count?: number;
  affected_file_count?: number;
  supported_finding_count?: number;
  ranking_explanation?: string;
  findings?: Finding[];
};
type Report = {
  schema_version?: string;
  analysis_scope?: string;
  total_files?: number;
  parsed_files?: number;
  failed_files?: number;
  finding_count?: number;
  group_count?: number;
  ranked_groups?: Group[];
  limitations?: string[];
};

const htmlEntities: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};
const esc = (value: unknown): string =>
  String(value ?? "").replace(/[&<>"']/g, (char) => htmlEntities[char] || char);
const count = (v: unknown): string =>
  Number.isFinite(Number(v)) ? String(v) : "—";

export class CodeQualityPanel {
  private static currentPanel: CodeQualityPanel | undefined;
  private readonly panel: vscode.WebviewPanel;
  private readonly context: vscode.ExtensionContext;
  private busy = false;
  private lastReport: Report | undefined;
  private workspace: vscode.WorkspaceFolder | undefined;

  public static show(context: vscode.ExtensionContext): void {
    if (this.currentPanel) {
      this.currentPanel.panel.reveal(vscode.ViewColumn.Beside);
      return;
    }
    this.currentPanel = new CodeQualityPanel(context);
  }

  private constructor(context: vscode.ExtensionContext) {
    this.context = context;
    this.workspace = vscode.workspace.workspaceFolders?.[0];
    this.panel = vscode.window.createWebviewPanel(
      "codeQualityPanel",
      "Maintainability Triage",
      vscode.ViewColumn.Beside,
      { enableScripts: true, retainContextWhenHidden: true },
    );
    this.panel.onDidDispose(() => {
      CodeQualityPanel.currentPanel = undefined;
    });
    this.panel.webview.onDidReceiveMessage(async (message) => {
      if (message?.type === "analyze") {
        await this.analyze();
      }
      if (message?.type === "selectWorkspace") {
        await this.selectWorkspace();
      }
      if (message?.type === "openSource") {
        await this.openSource(message.file, message.line);
      }
      if (message?.type === "explain") {
        await this.explainGroup(message.groupIndex);
      }
    });
    this.panel.webview.html = this.render();
  }

  private async selectWorkspace(): Promise<void> {
    const folders = vscode.workspace.workspaceFolders ?? [];
    if (!folders.length) {
      void vscode.window.showWarningMessage(
        "Open a Java repository folder in VS Code first.",
      );
      return;
    }
    const picked = await vscode.window.showQuickPick(
      folders.map((folder) => ({
        label: folder.name,
        description: folder.uri.fsPath,
        folder,
      })),
      { placeHolder: "Select the Java repository to analyze" },
    );
    if (picked) {
      this.workspace = picked.folder;
      this.panel.webview.html = this.render();
    }
  }

  private async openSource(file: unknown, line: unknown): Promise<void> {
    if (!this.workspace || typeof file !== "string" || !file) {
      return;
    }
    const root = path.resolve(this.workspace.uri.fsPath);
    const target = path.resolve(root, file);
    const relative = path.relative(root, target);
    if (
      relative === ".." ||
      relative.startsWith(".." + path.sep) ||
      path.isAbsolute(relative)
    ) {
      void vscode.window.showErrorMessage(
        "Source path is outside the selected repository.",
      );
      return;
    }
    try {
      const doc = await vscode.workspace.openTextDocument(
        vscode.Uri.file(target),
      );
      const editor = await vscode.window.showTextDocument(doc, {
        preview: false,
        viewColumn: vscode.ViewColumn.One,
      });
      const index = Math.max(
        0,
        Math.min(
          doc.lineCount - 1,
          Number.isFinite(Number(line)) ? Number(line) - 1 : 0,
        ),
      );
      const position = new vscode.Position(index, 0);
      editor.selection = new vscode.Selection(position, position);
      editor.revealRange(
        new vscode.Range(position, position),
        vscode.TextEditorRevealType.InCenter,
      );
    } catch (e) {
      void vscode.window.showErrorMessage(
        `Unable to open source: ${String(e)}`,
      );
    }
  }

  private async analyze(): Promise<void> {
    if (this.busy) {
      return;
    }
    if (!this.workspace) {
      await this.selectWorkspace();
      if (!this.workspace) {
        return;
      }
    }
    this.busy = true;
    this.lastReport = undefined;
    this.panel.webview.html = this.render(undefined, true);
    const analyzer = path.resolve(
      this.context.extensionPath,
      "..",
      "Code Cleanliness",
      "analyzer",
    );
    const reportFile = path.join(
      os.tmpdir(),
      `maintainability-${randomBytes(8).toString("hex")}.json`,
    );
    try {
      const classes = path.join(analyzer, "target", "classes");
      const dependencies = path.join(
        analyzer,
        "target",
        "runtime-classpath.txt",
      );
      await fs.access(
        path.join(
          classes,
          "lk",
          "sliit",
          "codecleanliness",
          "analysis",
          "MaintainabilityTriageCli.class",
        ),
      );
      const dependencyCp = (await fs.readFile(dependencies, "utf8")).trim();
      if (!dependencyCp) {
        throw new Error(
          "Runtime classpath is empty. Rebuild the Java analyzer first.",
        );
      }
      const classpath = [classes, dependencyCp].join(path.delimiter);
      const args = [
        "-cp",
        classpath,
        "lk.sliit.codecleanliness.analysis.MaintainabilityTriageCli",
        this.workspace.uri.fsPath,
        reportFile,
      ];
      await this.runJava(args, analyzer);
      const report = JSON.parse(
        await fs.readFile(reportFile, "utf8"),
      ) as Report;
      if (
        !Array.isArray(report.ranked_groups) ||
        String(report.schema_version) !== "1.1"
      ) {
        throw new Error(
          "Unsupported analyzer JSON. Expected schema 1.1 with ranked_groups.",
        );
      }
      this.lastReport = report;
      this.panel.webview.html = this.render(report);
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      this.panel.webview.html = this.render(undefined, false, detail);
      void vscode.window.showErrorMessage(
        `Maintainability analysis failed: ${detail.slice(0, 200)}`,
      );
    } finally {
      this.busy = false;
      await fs.rm(reportFile, { force: true }).catch(() => undefined);
    }
  }

  // Milestone 30B bridge: only send explicitly selected analyzer evidence to a LOCAL service.
  // Qwen inference is NOT bundled into this VS Code extension.
  private async explainGroup(indexValue: unknown): Promise<void> {
    const index = Number(indexValue);
    const sorted = [...(this.lastReport?.ranked_groups ?? [])].sort(
      (a, b) => (a.rank ?? 999999) - (b.rank ?? 999999),
    );
    if (!Number.isSafeInteger(index) || index < 0 || index >= sorted.length) {
      return;
    }
    const group = sorted[index];
    const respond = (status: "ok" | "error", text: string): void => {
      void this.panel.webview.postMessage({
        type: "explanation",
        index,
        status,
        text,
      });
    };
    // Fixed loopback endpoint: no automatic uploads to third parties or remote providers.
    const endpoint = "http://127.0.0.1:8765/explain";
    const payload = {
      task: "explain_maintainability_evidence",
      schema_version: "1.1",
      group: {
        rank: group.rank,
        ranking_explanation: group.ranking_explanation,
        findings: (group.findings ?? []).map((f) => ({
          concern: f.concern,
          symbol: f.symbol,
          rule_id: f.rule_id,
          description: f.description,
          evidence: f.evidence,
          source_file: f.source_file,
          start_line: f.start_line,
          end_line: f.end_line,
        })),
      },
      constraints: [
        "Use only the supplied evidence; do not invent measurements or developer intent.",
        "Distinguish potential refactoring from verified improvement.",
        "Do not claim that code behavior was tested or a finding was fixed.",
        "Describe uncertainty and recommend verification before editing code.",
      ],
    };
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 90000);
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new Error(`Inference service HTTP ${response.status}`);
      }
      const result: unknown = await response.json();
      if (
        !result ||
        typeof result !== "object" ||
        !("explanation" in result) ||
        typeof (result as { explanation: unknown }).explanation !== "string"
      ) {
        throw new Error(
          "Invalid inference response. Expected { explanation: string }.",
        );
      }
      const explanation = (
        result as { explanation: string }
      ).explanation.trim();
      if (!explanation) {
        throw new Error("The model returned an empty explanation.");
      }
      respond("ok", explanation.slice(0, 16000));
    } catch (error) {
      respond(
        "error",
        `Qwen service is not connected: ${error instanceof Error ? error.message : String(error)}. Analyzer findings remain available; no AI explanation has been generated.`,
      );
    } finally {
      clearTimeout(timeout);
    }
  }

  private runJava(args: string[], cwd: string): Promise<void> {
    return new Promise((resolve, reject) => {
      // No shell expansion: workspace paths with spaces and shell metacharacters remain safe.
      const child = spawn("java", args, {
        cwd,
        windowsHide: true,
        shell: false,
      });
      let stderr = "";
      let stdout = "";
      const maxOutput = 16000;
      child.stderr.on("data", (data) => {
        stderr = (stderr + String(data)).slice(-maxOutput);
      });
      child.stdout.on("data", (data) => {
        stdout = (stdout + String(data)).slice(-maxOutput);
      });
      child.on("error", (error) =>
        reject(
          new Error(
            `Could not start Java. Verify Java is on PATH. ${error.message}`,
          ),
        ),
      );
      child.on("close", (code) =>
        code === 0
          ? resolve()
          : reject(
              new Error(
                `Java analyzer exited ${code}: ${(stderr || stdout).slice(-2200)}`,
              ),
            ),
      );
    });
  }

  private render(report?: Report, loading = false, error?: string): string {
    const nonce = randomBytes(16).toString("base64");
    const groups = [...(report?.ranked_groups ?? [])].sort(
      (a, b) => (a.rank ?? 999999) - (b.rank ?? 999999),
    );
    const cards = groups
      .map((group, index) => {
        const findings = group.findings ?? [];
        const first = findings[0];
        const concerns = [
          ...new Set(findings.map((f) => f.concern).filter(Boolean)),
        ];
        const evidence = findings
          .map(
            (f) => `
        <div class="finding">
          <div class="finding-title"><span class="pill">${esc(f.concern)}</span><span class="minor">${esc(f.rule_id)}</span></div>
          <div class="detail">${esc(f.description)}</div>
          <div class="source-row"><button class="source" data-file="${esc(f.source_file)}" data-line="${esc(f.start_line)}" title="Open source at this line">${esc(f.source_file || "Unknown source")} : ${esc(f.start_line || "?")} ↗</button></div>
          <div class="metrics">${Object.entries(f.evidence ?? {})
            .map(
              ([k, v]) =>
                `<span class="metric"><b>${esc(k)}</b><em>${esc(v)}</em></span>`,
            )
            .join("")}</div>
        </div>`,
          )
          .join("");
        return `<article class="issue" data-search="${esc([first?.symbol, ...concerns, ...findings.map((f) => f.source_file)].join(" ").toLowerCase())}">
        <div class="issue-top"><span class="rank">#${esc(group.rank)}</span><div class="issue-main"><div class="symbol">${esc(first?.symbol || "Maintainability issue group")}</div><div class="issue-sub">${esc(concerns.join(" · "))} <span class="dot">·</span> ${findings.length} finding${findings.length === 1 ? "" : "s"}</div></div><span class="score">${Number.isFinite(Number(group.exceedance_score)) ? Number(group.exceedance_score).toFixed(2) : "—"}<small>exceedance</small></span></div>
        <details><summary>View evidence and ranking <span class="chev">⌄</span></summary><div class="expanded"><div class="why">${esc(group.ranking_explanation)}</div>${evidence}<div class="ai"><div class="ai-head"><strong>AI maintainability explanation</strong><span>Qwen · separate inference</span></div><button class="btn secondary explain" data-index="${index}">Generate explanation ↗</button><div class="ai-output" id="ai-${index}" role="status" aria-live="polite">No AI explanation generated. Connect the local Qwen service to enable this feature.</div></div></div></details>
      </article>`;
      })
      .join("");
    const loadingMarkup = loading
      ? '<div class="empty"><div class="spinner"></div><h3>Analyzing repository…</h3><p>Parsing Java files, detecting concerns, grouping findings, and ranking evidence.</p></div>'
      : "";
    const errorMarkup = error
      ? `<div class="alert"><strong>Analysis could not complete</strong><p>${esc(error)}</p><p>Build the analyzer in <code>Code Cleanliness/analyzer</code>, verify <code>target/runtime-classpath.txt</code>, and ensure Java is available.</p></div>`
      : "";
    const emptyMarkup =
      !report && !loading && !error
        ? '<div class="empty"><div class="hero-icon">⌁</div><h3>Understand what deserves attention</h3><p>Analyze the opened Java repository to reveal evidence-backed maintainability concerns and ranked issue groups.</p><p class="minor">Uses the existing Java analyzer. Preliminary thresholds; not verified ground-truth labels.</p></div>'
        : "";
    const nothingMarkup =
      report && !groups.length
        ? '<div class="empty"><h3>No issue groups reported</h3><p>No groups were produced with the current preliminary detection configuration.</p></div>'
        : "";
    return String.raw`<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';"><style nonce="${nonce}">
      :root{color-scheme:light dark}*{box-sizing:border-box}body{font:13px var(--vscode-font-family,system-ui);background:var(--vscode-editor-background);color:var(--vscode-editor-foreground);margin:0}.wrap{max-width:1020px;margin:auto;padding:28px 24px 60px}.eyebrow{font-size:10px;font-weight:750;letter-spacing:1.8px;text-transform:uppercase;color:var(--vscode-descriptionForeground)}.heading{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;margin:11px 0 23px}h1{font-size:26px;letter-spacing:-.6px;margin:0 0 7px;font-weight:700}.subtitle{color:var(--vscode-descriptionForeground);line-height:1.5;max-width:630px}.actions{display:flex;gap:8px;flex-wrap:wrap}.btn{border:1px solid var(--vscode-button-border,transparent);border-radius:7px;padding:9px 13px;font:inherit;font-weight:650;cursor:pointer;color:var(--vscode-button-foreground);background:var(--vscode-button-background);white-space:nowrap}.btn:hover{background:var(--vscode-button-hoverBackground)}.btn.secondary{background:var(--vscode-button-secondaryBackground);color:var(--vscode-button-secondaryForeground)}.btn.secondary:hover{background:var(--vscode-button-secondaryHoverBackground)}button:disabled{opacity:.6;cursor:wait}.workspace{display:flex;align-items:center;gap:8px;margin:14px 0 20px;color:var(--vscode-descriptionForeground);font-size:12px;overflow-wrap:anywhere}.indicator{width:7px;height:7px;border-radius:50%;background:var(--vscode-charts-green,#4fa680);flex-shrink:0}.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:11px;margin:12px 0 22px}.stat{border:1px solid var(--vscode-panel-border);border-radius:10px;background:var(--vscode-sideBar-background);padding:16px 15px;min-height:94px}.stat-label{font-size:11px;color:var(--vscode-descriptionForeground)}.stat-value{font-size:27px;font-weight:750;letter-spacing:-.6px;margin-top:11px;font-variant-numeric:tabular-nums}.section-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:24px 0 12px}.section-head h2{font-size:15px;margin:0}.count{color:var(--vscode-descriptionForeground);font-size:11px}.search{width:100%;padding:11px 12px;background:var(--vscode-input-background);color:var(--vscode-input-foreground);border:1px solid var(--vscode-input-border,var(--vscode-panel-border));border-radius:7px;font:inherit;outline-offset:2px}.issue{background:var(--vscode-sideBar-background);border:1px solid var(--vscode-panel-border);border-radius:9px;margin:10px 0;overflow:hidden}.issue-top{display:flex;align-items:center;gap:13px;padding:16px}.rank{flex:0 0 36px;background:var(--vscode-badge-background);color:var(--vscode-badge-foreground);border-radius:7px;text-align:center;padding:8px 0;font-size:12px;font-weight:750}.issue-main{flex:1;min-width:0}.symbol{font-weight:700;overflow-wrap:anywhere;line-height:1.5}.issue-sub{font-size:11px;color:var(--vscode-descriptionForeground);margin-top:4px;line-height:1.4}.dot{padding:0 4px}.score{font-size:18px;font-weight:750;font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}.score small{display:block;font-size:10px;font-weight:450;color:var(--vscode-descriptionForeground);margin-top:3px}details{border-top:1px solid var(--vscode-panel-border)}summary{cursor:pointer;padding:11px 16px;color:var(--vscode-textLink-foreground);font-size:12px;display:flex;justify-content:space-between;list-style:none}summary::-webkit-details-marker{display:none}.expanded{padding:3px 17px 15px}.why{font-size:11px;color:var(--vscode-descriptionForeground);line-height:1.65;margin:6px 0 16px}.finding{border-top:1px solid var(--vscode-panel-border);padding:13px 0}.finding-title{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.pill{border:1px solid var(--vscode-panel-border);border-radius:4px;padding:4px 7px;font-weight:700;font-size:10px;letter-spacing:.2px}.minor{font-size:11px;color:var(--vscode-descriptionForeground)}.detail{margin:9px 0;line-height:1.6}.source{background:transparent;border:0;color:var(--vscode-textLink-foreground);padding:0;cursor:pointer;text-align:left;font:inherit;overflow-wrap:anywhere}.source:hover{text-decoration:underline}.metrics{display:flex;flex-wrap:wrap;gap:7px;margin-top:11px}.metric{display:flex;gap:9px;align-items:center;background:var(--vscode-textCodeBlock-background);border-radius:5px;padding:7px 9px;font-size:11px}.metric b{font-weight:600;color:var(--vscode-descriptionForeground)}.metric em{font-style:normal;font-weight:700}.empty{padding:48px 25px;text-align:center;border:1px dashed var(--vscode-panel-border);border-radius:12px;margin-top:16px}.hero-icon{font-size:40px;color:var(--vscode-textLink-foreground)}.empty h3{font-size:16px;margin:13px 0 9px}.empty p{line-height:1.7;color:var(--vscode-descriptionForeground);max-width:470px;margin:8px auto}.alert{border:1px solid var(--vscode-inputValidation-errorBorder);border-radius:8px;padding:18px;margin-top:16px;overflow-wrap:anywhere}.alert p{line-height:1.6}.disclaimer{margin-top:22px;border-top:1px solid var(--vscode-panel-border);padding-top:14px;color:var(--vscode-descriptionForeground);font-size:11px;line-height:1.65}.spinner{margin:0 auto;width:28px;height:28px;border:3px solid var(--vscode-panel-border);border-top-color:var(--vscode-focusBorder);border-radius:50%;animation:spin .8s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:650px){.wrap{padding:18px 12px}.heading{display:block}.actions{margin-top:15px}.stats{grid-template-columns:repeat(2,minmax(0,1fr))}h1{font-size:22px}.score{font-size:15px}}
      .ai{border-top:1px solid var(--vscode-panel-border);padding:16px 0 4px}.ai-head{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:10px}.ai-head span{font-size:10px;color:var(--vscode-descriptionForeground)}.ai-output{margin-top:11px;padding:12px;border:1px solid var(--vscode-panel-border);background:var(--vscode-editor-background);border-radius:7px;line-height:1.7;white-space:normal;overflow-wrap:anywhere;color:var(--vscode-editor-foreground)}.ai-output h3{font-size:13px;margin:15px 0 7px;color:var(--vscode-foreground)}.ai-output p{margin:8px 0;line-height:1.7}.ai-output ul,.ai-output ol{padding-left:21px;margin:6px 0 13px}.ai-output li{margin:5px 0;line-height:1.65}.ai-output code{font-family:var(--vscode-editor-font-family,monospace);font-size:11px;background:var(--vscode-textCodeBlock-background);padding:2px 4px;border-radius:4px}.ai-output strong{font-weight:700}.ai-output .ai-note{font-size:11px;color:var(--vscode-descriptionForeground);border-top:1px solid var(--vscode-panel-border);padding-top:10px;margin-top:16px}.ai-output.error{color:var(--vscode-errorForeground)}
    </style></head><body><main class="wrap"><div class="eyebrow">CODE CLEANLINESS / MAINTAINABILITY</div><div class="heading"><div><h1>Maintainability Triage</h1><div class="subtitle">Repository-wide Java analysis · evidence-backed issues · provisional priority ordering</div></div><div class="actions"><button id="select" class="btn secondary">Change repository</button><button id="analyze" class="btn" ${loading ? "disabled" : ""}>${loading ? "Analyzing…" : report ? "Analyze again ↻" : "Analyze repository →"}</button></div></div><div class="workspace"><span class="indicator"></span><span>${esc(this.workspace?.uri.fsPath ?? "No repository selected — open a folder in VS Code")}</span></div>
    <div class="stats"><div class="stat"><div class="stat-label">Java files parsed</div><div class="stat-value">${report ? count(report.parsed_files) : "—"}</div></div><div class="stat"><div class="stat-label">Detected findings</div><div class="stat-value">${report ? count(report.finding_count) : "—"}</div></div><div class="stat"><div class="stat-label">Related issue groups</div><div class="stat-value">${report ? count(report.group_count) : "—"}</div></div><div class="stat"><div class="stat-label">Parse failures</div><div class="stat-value">${report ? count(report.failed_files) : "—"}</div></div></div>
    ${loadingMarkup}${errorMarkup}${emptyMarkup}${nothingMarkup}${report && groups.length ? `<div class="section-head"><h2>Ranked issue groups</h2><span class="count" id="visibleCount">${groups.length} groups</span></div><input class="search" id="search" placeholder="Search concerns, methods, or file names…" aria-label="Filter issue groups">${cards}` : ""}
    <div class="disclaimer">Analyzer configuration uses preliminary, uncalibrated thresholds. Findings and priority ranks are decision-support evidence, not independent ground truth or proven maintenance cost.${report?.limitations?.length ? "<p>" + report.limitations.map(esc).join(" · ") + "</p>" : ""}</div></main><script nonce="${nonce}">
      // Render a small, safe Markdown subset using DOM nodes (never model-controlled innerHTML).
      function inlineText(parent, line){
        const fragments=String(line).split(/(\*\*[^*]+\*\*|\x60[^\x60]+\x60)/g);
        fragments.forEach(part=>{let element;
          if(part.startsWith('**')&&part.endsWith('**')&&part.length>4){element=document.createElement('strong');element.textContent=part.slice(2,-2)}
          else if(part.startsWith(String.fromCharCode(96))&&part.endsWith(String.fromCharCode(96))&&part.length>2){element=document.createElement('code');element.textContent=part.slice(1,-1)}
          else{element=document.createTextNode(part)}parent.appendChild(element)
        });
      }
      function renderExplanation(slot, message){
        slot.replaceChildren();let list=null;let para=null;let inFence=false;let block=null;
        for(const rawLine of String(message).replace(/\r/g,'').split('\n')){
          const line=rawLine.trim();
          if(line.startsWith(String.fromCharCode(96).repeat(3))){inFence=!inFence;list=null;para=null;if(inFence){block=document.createElement('pre');block.style.whiteSpace='pre-wrap';block.style.overflowWrap='anywhere';slot.appendChild(block)}continue}
          if(inFence){block.appendChild(document.createTextNode(rawLine+'\n'));continue}
          if(!line){list=null;para=null;continue}
          const header=line.match(/^#{1,5}\s+(.+)$/);
          if(header){list=null;para=null;const h=document.createElement('h3');inlineText(h,header[1]);slot.appendChild(h);continue}
          const bullet=line.match(/^(?:[-*]\s+|\d+[.)]\s+)(.+)$/);
          if(bullet){para=null;const ordered=/^\d+[.)]/.test(line);const kind=ordered?'OL':'UL';if(!list||list.tagName!==kind){list=document.createElement(ordered?'ol':'ul');slot.appendChild(list)}const item=document.createElement('li');inlineText(item,bullet[1]);list.appendChild(item);continue}
          list=null;if(!para){para=document.createElement('p');slot.appendChild(para)}else{para.appendChild(document.createTextNode(' '))}inlineText(para,line)
        }
        const note=document.createElement('div');note.className='ai-note';note.textContent='AI-generated guidance · based on preliminary analyzer evidence · review source and test changes before refactoring.';slot.appendChild(note)
      }
      const vscode = acquireVsCodeApi();document.getElementById('analyze').addEventListener('click',()=>vscode.postMessage({type:'analyze'}));document.getElementById('select').addEventListener('click',()=>vscode.postMessage({type:'selectWorkspace'}));document.querySelectorAll('button.source').forEach(el=>el.addEventListener('click',()=>vscode.postMessage({type:'openSource',file:el.dataset.file,line:Number(el.dataset.line)})));document.querySelectorAll('button.explain').forEach(el=>el.addEventListener('click',()=>{const idx=Number(el.dataset.index);const slot=document.getElementById('ai-'+idx);slot.textContent='Requesting Qwen explanation…';slot.classList.remove('error');el.disabled=true;vscode.postMessage({type:'explain',groupIndex:idx})}));window.addEventListener('message',event=>{const msg=event.data;if(msg?.type!=='explanation')return;const slot=document.getElementById('ai-'+msg.index);if(!slot)return;if(msg.status==='ok'){renderExplanation(slot,msg.text)}else{slot.textContent=msg.text}slot.classList.toggle('error',msg.status==='error');const btn=document.querySelector('button.explain[data-index=\"'+msg.index+'\"]');if(btn)btn.disabled=false});const search=document.getElementById('search');if(search){search.addEventListener('input',()=>{let visible=0;document.querySelectorAll('article.issue').forEach(card=>{const show=card.dataset.search.includes(search.value.toLowerCase().trim());card.hidden=!show;if(show)visible++});document.getElementById('visibleCount').textContent=visible+' groups';})}
    </script></body></html>`;
  }
}
