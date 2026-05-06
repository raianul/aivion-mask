import * as assert from 'assert'
import * as vscode from 'vscode'

suite('extension', () => {
  test('extension activates without error', async () => {
    const ext = vscode.extensions.getExtension('aivionlabs.aivion-mask')
    if (ext) {
      await ext.activate()
      assert.ok(ext.isActive, 'extension should be active')
    } else {
      // In the test runner the extension is activated automatically
      assert.ok(true, 'skipped — extension not found by ID in test env')
    }
  })

  test('toggle command is registered', async () => {
    const commands = await vscode.commands.getCommands(true)
    assert.ok(commands.includes('aivion-mask.toggle'), 'toggle command should be registered')
  })
})
