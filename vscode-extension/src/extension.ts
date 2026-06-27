import * as vscode from "vscode";
import { DotApi } from "./api";
import { registerCommands, startDaemon } from "./commands";
import { ContextProvider } from "./contextProvider";
import { SidebarProvider } from "./sidebar";

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  const api = new DotApi();
  const config = vscode.workspace.getConfiguration("dot");

  registerCommands(context, api);

  // Auto-start the daemon for Dot-initialized workspaces.
  if (config.get<boolean>("autoStartDaemon", true) && !(await api.isUp())) {
    const root = vscode.workspace.workspaceFolders?.[0];
    if (root) {
      const dotDir = vscode.Uri.joinPath(root.uri, ".dot");
      try {
        await vscode.workspace.fs.stat(dotDir);
        startDaemon();
      } catch {
        // Not a Dot project; stay quiet.
      }
    }
  }

  const contextProvider = new ContextProvider(api);
  context.subscriptions.push(contextProvider);

  const sidebar = new SidebarProvider(api, contextProvider);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(SidebarProvider.viewType, sidebar)
  );

  // Expose Dot to Copilot Chat & friends via the Language Model tool API.
  if (config.get<boolean>("injectIntoCopilot", true)) {
    try {
      context.subscriptions.push(contextProvider.registerLanguageModelTool());
    } catch (error) {
      console.warn("dot: language model tool registration unavailable", error);
    }
  }

  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 90);
  status.text = "$(circle-filled) dot";
  status.command = "dot.showContext";
  context.subscriptions.push(status);

  const updateStatus = async () => {
    if (await api.isUp()) {
      const info = await api.status();
      status.text = "$(circle-filled) dot";
      status.tooltip = `Dot: ${info.files_indexed} files indexed, ${info.memories} memories`;
    } else {
      status.text = "$(circle-outline) dot";
      status.tooltip = "Dot daemon offline — run `dot daemon start`";
    }
    status.show();
  };
  void updateStatus();
  const poll = setInterval(() => void updateStatus(), 30_000);
  context.subscriptions.push({ dispose: () => clearInterval(poll) });
}

export function deactivate(): void {
  // subscriptions dispose automatically
}
