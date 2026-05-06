import * as vscode from 'vscode'
import { detect, mask } from './recognizers'

export type DetectHandler = (count: number, masked: string) => void

export class ClipboardMonitor {
  private timer: ReturnType<typeof setInterval> | undefined
  private lastText = ''

  constructor(private readonly onDetect: DetectHandler) {}

  start(intervalMs: number): void {
    if (this.timer !== undefined) return
    this.timer = setInterval(() => {
      void this.poll()
    }, intervalMs)
  }

  stop(): void {
    if (this.timer !== undefined) {
      clearInterval(this.timer)
      this.timer = undefined
    }
  }

  get running(): boolean {
    return this.timer !== undefined
  }

  private async poll(): Promise<void> {
    let text: string
    try {
      text = await vscode.env.clipboard.readText()
    } catch {
      return // clipboard read can fail for non-text content
    }
    if (text === this.lastText) return
    this.lastText = text

    const matches = detect(text)
    if (matches.length === 0) return

    const masked = mask(text, matches)
    this.onDetect(matches.length, masked)
  }

  // Called by extension after writing masked text to clipboard in block mode,
  // so the next poll doesn't re-detect the already-masked content.
  updateLastText(text: string): void {
    this.lastText = text
  }
}
