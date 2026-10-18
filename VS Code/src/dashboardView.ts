import * as vscode from 'vscode';

export class DashboardItem extends vscode.TreeItem {
  constructor(
    public readonly label: string,
    public readonly iconName: string,
    public readonly commandId: string,
    public readonly subTitle: string
  ) {
    super(label, vscode.TreeItemCollapsibleState.None);
    this.description = subTitle;
    this.iconPath = new vscode.ThemeIcon(iconName);
    this.command = {
      command: commandId,
      title: label
    };
  }
}

export class DashboardProvider implements vscode.TreeDataProvider<DashboardItem> {
  getTreeItem(element: DashboardItem): vscode.TreeItem {
    return element;
  }

  getChildren(): Thenable<DashboardItem[]> {
    return Promise.resolve([
      new DashboardItem('Architecture', 'type-hierarchy', 'analyzer.openArchitecture', 'Launch Window'),
      new DashboardItem('Code Quality', 'checklist', 'analyzer.openCodeQuality', 'Launch Window'),
      new DashboardItem('Behavioural', 'pulse', 'analyzer.openBehavioural', 'Launch Window'),
      new DashboardItem('Runtime Errors', 'bug', 'analyzer.openRuntime', 'Launch Window')
    ]);
  }
}