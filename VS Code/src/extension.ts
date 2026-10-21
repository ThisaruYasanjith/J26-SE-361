import * as vscode from "vscode";
import { DashboardProvider } from "./dashboardView";
import { ArchitecturePanel } from "./architecture/architecturePanel";
import { CodeQualityPanel } from "./codeQuality/codeQualityPanel";
import { BehaviouralPanel } from "./behavioural/behaviouralPanel";
import { RuntimePanel } from "./runtime/runtimePanel";
import { AnalyzerRunner } from "./architecture/analyzerRunner";
import { ProjectAnalysisWorkflow } from "./architecture/analysisWorkflow";
import { ArchitectureBackendClient, DEFAULT_BACKEND_URL } from "./architecture/backendClient";
import { ProjectContextSyncWorkflow } from "./architecture/contextSyncWorkflow";
import { ConformanceWorkflow } from "./architecture/conformanceWorkflow";
import { VscodeConformanceDiagnostics } from "./architecture/conformanceDiagnostics";

export function activate(context: vscode.ExtensionContext) {
  const architectureOutput = vscode.window.createOutputChannel("Architecture Governance");
  context.subscriptions.push(architectureOutput);
  const analysis = new ProjectAnalysisWorkflow(new AnalyzerRunner(context.extensionPath, architectureOutput), {
    folders: () => vscode.workspace.workspaceFolders?.map(folder => ({
      name: folder.name, fsPath: folder.uri.fsPath, scheme: folder.uri.scheme,
    })),
    choose: async folders => {
      const chosen = await vscode.window.showQuickPick(folders.map(folder => ({
        label: folder.name, description: folder.fsPath, folder,
      })), { title: "Select project to analyze", placeHolder: "Choose an opened Java project folder" });
      return chosen?.folder;
    },
    progress: async (task, cancel) => vscode.window.withProgress({
      location: vscode.ProgressLocation.Notification, title: "Analyzing Spring Boot architecture...", cancellable: true,
    }, async (_progress, token) => {
      const subscription = token.onCancellationRequested(cancel);
      try {
        if (token.isCancellationRequested) { cancel(); }
        return await task();
      } finally { subscription.dispose(); }
    }),
    showError: message => { void vscode.window.showErrorMessage(message); },
  });
  context.subscriptions.push(analysis);
  const syncClient = new ArchitectureBackendClient(
    () => vscode.workspace.getConfiguration('architectureGovernance').get<string>('aiBackendUrl', DEFAULT_BACKEND_URL),
    architectureOutput,
  );
  const contextSync = new ProjectContextSyncWorkflow(analysis, syncClient, architectureOutput);
  context.subscriptions.push(syncClient, contextSync, vscode.workspace.onDidChangeConfiguration(event => {
    if (event.affectsConfiguration('architectureGovernance.aiBackendUrl')) { contextSync.reset(); }
  }));
  const diagnostics = new VscodeConformanceDiagnostics(architectureOutput);
  const conformance = new ConformanceWorkflow(analysis, contextSync, syncClient, diagnostics, architectureOutput, {
    progress: async (task, cancel) => vscode.window.withProgress({
      location: vscode.ProgressLocation.Notification, title: "Checking architecture conformance...", cancellable: true,
    }, async (_progress, token) => {
      const subscription = token.onCancellationRequested(cancel);
      try {
        if (token.isCancellationRequested) { cancel(); }
        await task();
      } finally { subscription.dispose(); }
    }),
  });
  context.subscriptions.push(conformance, diagnostics, vscode.workspace.onDidChangeWorkspaceFolders(() => {
    if (analysis.state.status === 'succeeded') {
      const root = analysis.state.summary.projectRoot;
      if (!vscode.workspace.workspaceFolders?.some(folder => folder.uri.fsPath === root)) { contextSync.reset(); }
    }
  }));
  // Register sidebar buttons view
  vscode.window.registerTreeDataProvider(
    "analyzer.dashboardView",
    new DashboardProvider(),
  );

  // Register commands to open each full window panel
  context.subscriptions.push(
    vscode.commands.registerCommand("analyzer.openArchitecture", () => {
      ArchitecturePanel.show(context, architectureOutput, analysis, contextSync, conformance);
    }),
    vscode.commands.registerCommand("architectureGovernance.analyzeProject", async () => {
      ArchitecturePanel.show(context, architectureOutput, analysis, contextSync, conformance);
      await analysis.run();
    }),
    vscode.commands.registerCommand("architectureGovernance.checkConformance", async () => {
      ArchitecturePanel.show(context, architectureOutput, analysis, contextSync, conformance);
      await conformance.run();
    }),
    vscode.commands.registerCommand("analyzer.openCodeQuality", () => {
      CodeQualityPanel.show(context);
    }),
    vscode.commands.registerCommand("analyzer.openBehavioural", () => {
      BehaviouralPanel.show(context);
    }),
    vscode.commands.registerCommand("analyzer.openRuntime", () => {
      RuntimePanel.show(context);
    }),
  );
}

export function deactivate() {}
