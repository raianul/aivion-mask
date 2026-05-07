import * as vscode from 'vscode'

export function registerCommands(
  context: vscode.ExtensionContext,
  onToggle: () => void
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand('aivion-mask.toggle', onToggle)
  )
  context.subscriptions.push(
    vscode.commands.registerCommand('aivion-mask.stopSidecar', () => {
      void vscode.window.showInformationMessage(
        'Aivion Mask: sidecar runs as a system service. Stop it via launchctl / systemctl or Task Scheduler.'
      )
    })
  )
}
