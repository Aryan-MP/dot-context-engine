import * as vscode from "vscode";
import { DotApi } from "./api";
import { relativeActiveFile } from "./contextProvider";

export function registerCommands(
  context: vscode.ExtensionContext,
  api: DotApi
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand("dot.captureDecision", async () => {
      const editor = vscode.window.activeTextEditor;
      const selected = editor?.document.getText(editor.selection) ?? "";
      const content = await vscode.window.showInputBox({
        title: "Capture decision",
        prompt: "What was decided, and why?",
        value: selected.trim().slice(0, 500),
        ignoreFocusOut: true,
      });
      if (!content) return;
      const kind =
        (await vscode.window.showQuickPick(
          ["decision", "rejected", "action_item", "note"],
          { title: "Kind of memory" }
        )) ?? "decision";
      try {
        await api.captureMemory(content, kind, relativeActiveFile() ?? "");
        vscode.window.showInformationMessage("Dot captured the decision.");
      } catch (error) {
        vscode.window.showErrorMessage(`Dot: capture failed - ${String(error)}`);
      }
    }),

    vscode.commands.registerCommand("dot.showContext", async () => {
      const file = relativeActiveFile();
      try {
        const markdown = await api.contextFormatted("", file, "markdown");
        const document = await vscode.workspace.openTextDocument({
          content: markdown,
          language: "markdown",
        });
        await vscode.window.showTextDocument(document, { preview: true });
      } catch (error) {
        vscode.window.showErrorMessage(`Dot: ${String(error)}`);
      }
    }),

    vscode.commands.registerCommand("dot.sync", async () => {
      try {
        await api.sync();
        vscode.window.showInformationMessage("Dot: re-index started.");
      } catch (error) {
        vscode.window.showErrorMessage(`Dot: sync failed - ${String(error)}`);
      }
    }),

    vscode.commands.registerCommand("dot.startDaemon", () => startDaemon()),

    vscode.commands.registerCommand("dot.stopDaemon", () => {
      runDotCli(["daemon", "stop"]);
    }),

    vscode.commands.registerCommand("dot.openDashboard", () => {
      const base = vscode.workspace
        .getConfiguration("dot")
        .get<string>("apiUrl", "http://127.0.0.1:7337");
      void vscode.env.openExternal(vscode.Uri.parse(`${base}/ui`));
    })
  );
}

export function startDaemon(): void {
  runDotCli(["daemon", "start"]);
}

function runDotCli(args: string[]): void {
  const cwd = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!cwd) {
    vscode.window.showWarningMessage("Dot: open a workspace folder first.");
    return;
  }
  const terminal = vscode.window.createTerminal({ name: "dot", cwd, hideFromUser: true });
  terminal.sendText(`dot ${args.join(" ")}`, true);
}
