import * as vscode from "vscode";
import { DashboardProvider } from "./dashboardView";
import { ArchitecturePanel } from "./architecture/architecturePanel";
import { CodeQualityPanel } from "./codeQuality/codeQualityPanel";
import { BehaviouralPanel } from "./behavioural/behaviouralPanel";
import { RuntimePanel } from "./runtime/runtimePanel";

export function activate(context: vscode.ExtensionContext) {
  const architectureOutput = vscode.window.createOutputChannel("Architecture Governance");
  context.subscriptions.push(architectureOutput);
  // Register sidebar buttons view
  vscode.window.registerTreeDataProvider(
    "analyzer.dashboardView",
    new DashboardProvider(),
  );

  // Register commands to open each full window panel
  context.subscriptions.push(
    vscode.commands.registerCommand("analyzer.openArchitecture", () => {
      ArchitecturePanel.show(context, architectureOutput);
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
