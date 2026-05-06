import * as vscode from 'vscode'

export function registerCommands(
  context: vscode.ExtensionContext,
  onToggle: () => void
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand('aivion-mask.toggle', onToggle)
  )
}
