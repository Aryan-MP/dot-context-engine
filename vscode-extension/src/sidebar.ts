import * as vscode from "vscode";
import { DotApi, DotContext } from "./api";
import { ContextProvider } from "./contextProvider";

/** "What Dot knows about this file" — webview in the activity bar. */
export class SidebarProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "dot.sidebarView";
  private view: vscode.WebviewView | undefined;

  constructor(
    private readonly api: DotApi,
    private readonly contextProvider: ContextProvider
  ) {
    contextProvider.onContextChanged((context) => this.render(context));
  }

  resolveWebviewView(view: vscode.WebviewView): void {
    this.view = view;
    view.webview.options = { enableScripts: true };
    view.webview.onDidReceiveMessage(async (message) => {
      if (message.type === "open") {
        const root = vscode.workspace.workspaceFolders?.[0]?.uri;
        if (!root) return;
        const uri = vscode.Uri.joinPath(root, message.file);
        const document = await vscode.workspace.openTextDocument(uri);
        const editor = await vscode.window.showTextDocument(document);
        const line = Math.max(0, (message.line ?? 1) - 1);
        editor.revealRange(new vscode.Range(line, 0, line, 0), vscode.TextEditorRevealType.AtTop);
      } else if (message.type === "sync") {
        await vscode.commands.executeCommand("dot.sync");
      }
    });
    this.render(this.contextProvider.currentContext);
  }

  private render(context: DotContext | undefined): void {
    if (!this.view) return;
    this.view.webview.html = this.html(context);
  }

  private html(context: DotContext | undefined): string {
    const body = context ? renderContext(context) : renderOffline();
    return `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); font-size: 12px; padding: 6px; }
  h3 { margin: 10px 0 4px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; opacity: 0.8; }
  .item { padding: 5px 6px; margin-bottom: 4px; border-radius: 4px; background: var(--vscode-editorWidget-background); cursor: pointer; }
  .item:hover { background: var(--vscode-list-hoverBackground); }
  .meta { opacity: 0.65; font-size: 11px; }
  .kind { display: inline-block; padding: 0 5px; border-radius: 6px; background: var(--vscode-badge-background); color: var(--vscode-badge-foreground); font-size: 10px; margin-right: 4px; }
  .empty { opacity: 0.7; padding: 8px 0; }
  button { background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; padding: 4px 10px; border-radius: 3px; cursor: pointer; }
</style>
</head>
<body>
${body}
<script>
  const vscode = acquireVsCodeApi();
  for (const el of document.querySelectorAll('[data-file]')) {
    el.addEventListener('click', () => vscode.postMessage({
      type: 'open', file: el.dataset.file, line: Number(el.dataset.line || 1)
    }));
  }
  document.getElementById('sync')?.addEventListener('click', () => vscode.postMessage({ type: 'sync' }));
</script>
</body>
</html>`;
  }
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderOffline(): string {
  return `<div class="empty">Dot daemon isn't reachable.<br/><br/>
Start it with <code>dot daemon start</code> in your project, or run
the <b>Dot: Start Daemon</b> command.</div>`;
}

function renderContext(context: DotContext): string {
  const decisions = context.decisions
    .map(
      (decision) => `
    <div class="item" ${decision.file_path ? `data-file="${escapeHtml(decision.file_path)}"` : ""}>
      <span class="kind">${escapeHtml(decision.kind)}</span>
      ${escapeHtml(truncate(decision.content, 220))}
      <div class="meta">${escapeHtml(decision.source)} · weight ${decision.weight.toFixed(2)}</div>
    </div>`
    )
    .join("");

  const related = context.chunks
    .filter((chunk) => chunk.file_path !== context.current_file)
    .slice(0, 8)
    .map(
      (chunk) => `
    <div class="item" data-file="${escapeHtml(chunk.file_path)}" data-line="${chunk.start_line}">
      <b>${escapeHtml(chunk.symbol)}</b>
      <div class="meta">${escapeHtml(chunk.file_path)}:${chunk.start_line} · relevance ${chunk.score.toFixed(2)}</div>
    </div>`
    )
    .join("");

  return `
  <div class="meta">context for <b>${escapeHtml(context.current_file ?? "workspace")}</b>
   · ${context.tokens_used}/${context.token_budget} tokens · ${context.assembly_ms.toFixed(0)}ms</div>
  <h3>Decisions</h3>
  ${decisions || '<div class="empty">No captured decisions relevant here yet.</div>'}
  <h3>Related code</h3>
  ${related || '<div class="empty">Nothing indexed nearby yet.</div>'}
  <p><button id="sync">Re-index project</button></p>`;
}

function truncate(text: string, max: number): string {
  const flat = text.replace(/\s+/g, " ");
  return flat.length > max ? flat.slice(0, max - 1) + "…" : flat;
}
