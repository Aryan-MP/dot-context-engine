import * as vscode from "vscode";
import { DotApi, DotContext } from "./api";

/**
 * Bridges Dot into the AI tooling inside VS Code:
 *
 * - queries the Dot daemon whenever the active editor changes, caching the
 *   assembled context for the sidebar and decorations
 * - registers a Language Model tool ("dot-context_lookup") so Copilot Chat
 *   and other LM API consumers can pull project memory on demand
 * - decorates lines that have captured decisions attached
 */
export class ContextProvider implements vscode.Disposable {
  private readonly disposables: vscode.Disposable[] = [];
  private readonly emitter = new vscode.EventEmitter<DotContext | undefined>();
  readonly onContextChanged = this.emitter.event;
  private current: DotContext | undefined;
  private readonly decorationType: vscode.TextEditorDecorationType;

  constructor(private readonly api: DotApi) {
    this.decorationType = vscode.window.createTextEditorDecorationType({
      gutterIconSize: "contain",
      overviewRulerColor: new vscode.ThemeColor("editorInfo.foreground"),
      after: {
        contentText: "  ● dot",
        color: new vscode.ThemeColor("editorCodeLens.foreground"),
        fontStyle: "italic",
      },
    });

    this.disposables.push(
      vscode.window.onDidChangeActiveTextEditor((editor) => {
        void this.refresh(editor);
      }),
      vscode.workspace.onDidSaveTextDocument(() => {
        void this.refresh(vscode.window.activeTextEditor);
      })
    );
    void this.refresh(vscode.window.activeTextEditor);
  }

  get currentContext(): DotContext | undefined {
    return this.current;
  }

  registerLanguageModelTool(): vscode.Disposable {
    return vscode.lm.registerTool("dot-context_lookup", {
      invoke: async (options: vscode.LanguageModelToolInvocationOptions<{ query: string }>) => {
        const file = relativeActiveFile();
        const formatted = await this.api.contextFormatted(
          options.input.query,
          file,
          "markdown"
        );
        return new vscode.LanguageModelToolResult([
          new vscode.LanguageModelTextPart(formatted),
        ]);
      },
    });
  }

  private async refresh(editor: vscode.TextEditor | undefined): Promise<void> {
    if (!editor || editor.document.uri.scheme !== "file") {
      return;
    }
    const file = relativePath(editor.document.uri);
    try {
      const budget = vscode.workspace.getConfiguration("dot").get<number>("tokenBudget", 4000);
      this.current = await this.api.context("", file, budget);
      this.emitter.fire(this.current);
      this.decorate(editor, file);
    } catch {
      this.current = undefined;
      this.emitter.fire(undefined);
    }
  }

  /** Highlight lines in the active file that have captured decisions. */
  private decorate(editor: vscode.TextEditor, file: string | undefined): void {
    if (!this.current || !file) return;
    const ranges: vscode.DecorationOptions[] = [];
    for (const decision of this.current.decisions) {
      if (decision.file_path !== file) continue;
      ranges.push({
        range: new vscode.Range(0, 0, 0, 0),
        hoverMessage: new vscode.MarkdownString(
          `**Dot ${decision.kind}** (${decision.source})\n\n${decision.content}`
        ),
      });
    }
    for (const chunk of this.current.chunks) {
      if (chunk.file_path !== file || chunk.kind !== "comment") continue;
      const line = Math.max(0, chunk.start_line - 1);
      ranges.push({
        range: new vscode.Range(line, 0, line, 0),
        hoverMessage: new vscode.MarkdownString(
          `**Dot captured context**\n\n\`\`\`\n${chunk.content}\n\`\`\``
        ),
      });
    }
    editor.setDecorations(this.decorationType, ranges);
  }

  dispose(): void {
    this.decorationType.dispose();
    this.emitter.dispose();
    for (const disposable of this.disposables) disposable.dispose();
  }
}

export function relativePath(uri: vscode.Uri): string | undefined {
  const folder = vscode.workspace.getWorkspaceFolder(uri);
  if (!folder) return undefined;
  return vscode.workspace.asRelativePath(uri, false);
}

export function relativeActiveFile(): string | undefined {
  const editor = vscode.window.activeTextEditor;
  return editor ? relativePath(editor.document.uri) : undefined;
}
