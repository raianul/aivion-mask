import * as vscode from 'vscode'
import * as os from 'os'
import * as path from 'path'
import * as fs from 'fs'
import { execFile, spawn } from 'child_process'
import { promisify } from 'util'

const execFileAsync = promisify(execFile)

export const AIVION_DIR = path.join(os.homedir(), '.aivion-mask')
const VENV_DIR = path.join(AIVION_DIR, 'venv')
const PID_FILE = path.join(AIVION_DIR, 'sidecar.pid')
export const SIDECAR_PORT = 47474
const HEALTH_URL = `http://localhost:${SIDECAR_PORT}/health`

function venvBin(name: string): string {
  return process.platform === 'win32'
    ? path.join(VENV_DIR, 'Scripts', `${name}.exe`)
    : path.join(VENV_DIR, 'bin', name)
}

export async function isHealthy(): Promise<boolean> {
  try {
    const res = await fetch(HEALTH_URL, { signal: AbortSignal.timeout(2000) })
    return res.ok
  } catch {
    return false
  }
}

async function waitUntilHealthy(timeoutMs = 30_000): Promise<boolean> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (await isHealthy()) return true
    await new Promise<void>((r) => setTimeout(r, 500))
  }
  return false
}

async function installVenv(
  progress: vscode.Progress<{ message?: string }>
): Promise<void> {
  fs.mkdirSync(AIVION_DIR, { recursive: true })
  progress.report({ message: 'Creating Python venv...' })
  await execFileAsync('python3', ['-m', 'venv', VENV_DIR])
  progress.report({ message: 'Installing aivion-mask-sidecar (first time only)...' })
  await execFileAsync(venvBin('pip'), ['install', '--quiet', 'aivion-mask-sidecar'])
}

function spawnSidecar(): void {
  const proc = spawn(venvBin('aivion-mask-sidecar'), [], {
    detached: true,
    stdio: 'ignore',
  })
  proc.unref()
  if (proc.pid !== undefined) {
    fs.mkdirSync(AIVION_DIR, { recursive: true })
    fs.writeFileSync(PID_FILE, String(proc.pid))
  }
}

async function registerSystemService(): Promise<void> {
  try {
    if (process.platform === 'darwin') await registerLaunchd()
    else if (process.platform === 'linux') await registerSystemd()
    else if (process.platform === 'win32') await registerTaskScheduler()
  } catch {
    // System service registration is best-effort — sidecar still works without it
  }
}

async function registerLaunchd(): Promise<void> {
  const plistDir = path.join(os.homedir(), 'Library', 'LaunchAgents')
  const plistPath = path.join(plistDir, 'com.aivionlabs.mask.plist')
  if (fs.existsSync(plistPath)) return
  fs.mkdirSync(plistDir, { recursive: true })
  fs.writeFileSync(
    plistPath,
    `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.aivionlabs.mask</string>
  <key>ProgramArguments</key>
  <array><string>${venvBin('aivion-mask-sidecar')}</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
</dict>
</plist>`
  )
  await execFileAsync('launchctl', ['load', plistPath]).catch(() => {})
}

async function registerSystemd(): Promise<void> {
  const serviceDir = path.join(os.homedir(), '.config', 'systemd', 'user')
  const servicePath = path.join(serviceDir, 'aivion-mask.service')
  if (fs.existsSync(servicePath)) return
  fs.mkdirSync(serviceDir, { recursive: true })
  fs.writeFileSync(
    servicePath,
    `[Unit]
Description=Aivion Mask local PII sidecar

[Service]
ExecStart=${venvBin('aivion-mask-sidecar')}
Restart=on-failure

[Install]
WantedBy=default.target
`
  )
  await execFileAsync('systemctl', ['--user', 'enable', '--now', 'aivion-mask']).catch(() => {})
}

async function registerTaskScheduler(): Promise<void> {
  const taskName = 'AivionMaskSidecar'
  try {
    await execFileAsync('schtasks', ['/query', '/tn', taskName])
    return
  } catch {
    // not registered — proceed
  }
  await execFileAsync('schtasks', [
    '/create', '/tn', taskName,
    '/tr', venvBin('aivion-mask-sidecar'),
    '/sc', 'ONLOGON',
    '/f',
  ]).catch(() => {})
}

export class SidecarManager {
  async ensureRunning(): Promise<boolean> {
    if (await isHealthy()) return true

    return vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: 'Aivion Mask', cancellable: false },
      async (progress) => {
        if (!fs.existsSync(venvBin('aivion-mask-sidecar'))) {
          try {
            await installVenv(progress)
          } catch (err) {
            void vscode.window.showErrorMessage(`Aivion Mask: sidecar install failed — ${err}`)
            return false
          }
        }

        progress.report({ message: 'Starting sidecar...' })
        spawnSidecar()
        void registerSystemService()

        const ready = await waitUntilHealthy()
        if (!ready) {
          void vscode.window.showErrorMessage(
            'Aivion Mask: sidecar failed to start. Check the Output panel.'
          )
          return false
        }
        return true
      }
    )
  }
}
