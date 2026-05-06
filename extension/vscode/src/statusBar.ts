import * as vscode from 'vscode'

export class MaskStatusBar {
  private readonly item: vscode.StatusBarItem

  constructor() {
    this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100)
    this.item.command = 'aivion-mask.toggle'
    this.setActive()
    this.item.show()
  }

  setActive(): void {
    this.item.text = '$(shield) aivion-mask'
    this.item.tooltip = 'Aivion Mask active — click to toggle off'
    this.item.backgroundColor = undefined
    this.item.color = undefined
  }

  setDisabled(): void {
    this.item.text = '$(shield) aivion-mask: off'
    this.item.tooltip = 'Aivion Mask disabled — click to enable'
    this.item.color = new vscode.ThemeColor('statusBarItem.warningForeground')
  }

  setDetected(count: number): void {
    const noun = count === 1 ? 'secret' : 'secrets'
    this.item.text = `$(shield) ${count} ${noun} masked`
    this.item.tooltip = `${count} ${noun} redacted from clipboard`
    this.item.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground')
    // Reset to normal state after 3 s
    setTimeout(() => this.setActive(), 3000)
  }

  dispose(): void {
    this.item.dispose()
  }
}
