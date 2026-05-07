import * as vscode from 'vscode'
import { ClipboardMonitor } from './clipboard'
import { MaskStatusBar } from './statusBar'
import { registerCommands } from './commands'
import { SidecarManager, SIDECAR_PORT } from './sidecar'

let monitor: ClipboardMonitor | undefined
let statusBar: MaskStatusBar | undefined
let enabled = true

export function activate(context: vscode.ExtensionContext): void {
  const config = () => vscode.workspace.getConfiguration('aivion-mask')

  statusBar = new MaskStatusBar()
  context.subscriptions.push(statusBar)

  enabled = config().get('clipboard.enabled', true)

  monitor = new ClipboardMonitor((count, masked) => {
    const mode = config().get<string>('clipboard.mode', 'warn')

    if (mode === 'block') {
      void vscode.env.clipboard.writeText(masked).then(() => {
        monitor?.updateLastText(masked)
      })
      statusBar?.setDetected(count)
    } else {
      const noun = count === 1 ? 'secret' : 'secrets'
      void vscode.window
        .showWarningMessage(
          `Aivion Mask: ${count} ${noun} detected in clipboard`,
          'Block now',
          'Dismiss'
        )
        .then((action) => {
          if (action === 'Block now') {
            void vscode.env.clipboard.writeText(masked)
          }
        })
      statusBar?.setDetected(count)
    }
  })

  if (enabled) {
    const intervalMs = config().get<number>('clipboard.pollIntervalMs', 500)
    monitor.start(intervalMs)
  } else {
    statusBar.setDisabled()
  }

  registerCommands(context, () => {
    enabled = !enabled
    if (enabled) {
      const intervalMs = config().get<number>('clipboard.pollIntervalMs', 500)
      monitor?.start(intervalMs)
      statusBar?.setActive()
      void vscode.window.showInformationMessage('Aivion Mask: enabled')
    } else {
      monitor?.stop()
      statusBar?.setDisabled()
      void vscode.window.showInformationMessage('Aivion Mask: disabled')
    }
  })

  const sidecarManager = new SidecarManager()
  void sidecarManager.ensureRunning().then((running) => {
    if (running) statusBar?.setProxyActive(SIDECAR_PORT)
  })

  // Restart monitor if poll interval config changes
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration('aivion-mask.clipboard.pollIntervalMs') && enabled) {
        monitor?.stop()
        const intervalMs = config().get<number>('clipboard.pollIntervalMs', 500)
        monitor?.start(intervalMs)
      }
    })
  )
}

export function deactivate(): void {
  monitor?.stop()
}
