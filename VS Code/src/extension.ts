import * as vscode from "vscode";
import { DashboardProvider } from "./dashboardView";
import { ArchitecturePanel } from "./architecture/architecturePanel";
import { CodeQualityPanel } from "./codeQuality/codeQualityPanel";
import { BehaviouralPanel } from "./behavioural/behaviouralPanel";
import { ExceptionsPanel } from "./exceptions/exceptionsPanel";

export function activate(context: vscode.ExtensionContext) {
  // Register sidebar buttons view
  vscode.window.registerTreeDataProvider(
    "analyzer.dashboardView",
    new DashboardProvider(),
  );

  // Register commands to open each full window panel
  context.subscriptions.push(
    vscode.commands.registerCommand("analyzer.openArchitecture", () => {
      ArchitecturePanel.show(context);
    }),
    vscode.commands.registerCommand("analyzer.openCodeQuality", () => {
      CodeQualityPanel.show(context);
    }),
    vscode.commands.registerCommand("analyzer.openBehavioural", () => {
      BehaviouralPanel.show(context);
    }),
    vscode.commands.registerCommand("analyzer.openExceptions", () => {
      ExceptionsPanel.show(context);
    }),
  );
}

export function deactivate() {}
