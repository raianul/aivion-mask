import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import * as vscode from 'vscode'

const AIVION_DIR = path.join(os.homedir(), '.aivion-mask')
const CONFIG_PATH = path.join(AIVION_DIR, 'config.toml')

interface CustomPattern {
  name: string
  pattern: string
  abbrev?: string
}

function buildToml(
  apiBase: string,
  apiKey: string,
  unmaskResponse: boolean,
  customPatterns: CustomPattern[]
): string {
  let toml = `[sidecar]
port = 47474
session_ttl_hours = 8
idle_shutdown_minutes = 0
unmask_response = ${unmaskResponse ? 'true' : 'false'}
`
  for (const p of customPatterns) {
    toml += `
[[sidecar.custom_patterns]]
name = "${p.name}"
pattern = '${p.pattern}'`
    if (p.abbrev) {
      toml += `\nabbrev = "${p.abbrev}"`
    }
    toml += '\n'
  }

  toml += `
[llm]
api_base = "${apiBase}"
api_key = "${apiKey}"
`
  return toml
}

export function syncConfig(): void {
  const cfg = vscode.workspace.getConfiguration('aivion-mask')
  const apiBase = cfg.get<string>('llm.apiBase', 'https://api.openai.com/v1')
  const apiKey = cfg.get<string>('llm.apiKey', '')
  const unmaskResponse = cfg.get<boolean>('sidecar.unmaskResponse', true)
  const customPatterns = cfg.get<CustomPattern[]>('sidecar.customPatterns', [])

  fs.mkdirSync(AIVION_DIR, { recursive: true })
  fs.writeFileSync(CONFIG_PATH, buildToml(apiBase, apiKey, unmaskResponse, customPatterns), {
    mode: 0o600,
  })
}
