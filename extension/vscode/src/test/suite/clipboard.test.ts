import * as assert from 'assert'
import { detect, mask } from '../../recognizers'

// ClipboardMonitor requires a live VS Code environment for vscode.env.clipboard.
// We test the detect+mask logic (the core) here independently.

suite('clipboard logic', () => {
  test('mask replaces postgres URL password', () => {
    const text = 'connect to postgresql://admin:SuperSecret@db.internal:5432/prod'
    const matches = detect(text)
    const result = mask(text, matches)
    assert.ok(!result.includes('SuperSecret'), 'password removed')
    assert.ok(result.includes('[REDACTED:DATABASE_URL_POSTGRES]'), 'postgres type labeled')
  })

  test('mask replaces GitHub PAT', () => {
    const text = `TOKEN=ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890`
    const matches = detect(text)
    const result = mask(text, matches)
    assert.ok(!result.includes('ghp_'), 'token removed')
    assert.ok(result.includes('[REDACTED:GITHUB_PAT]'), 'type labeled')
  })

  test('detect returns empty for clean text', () => {
    const matches = detect('just a normal string with no secrets at all')
    assert.strictEqual(matches.length, 0)
  })

  test('mask is idempotent on already-masked text', () => {
    const masked = 'connect to [REDACTED:DATABASE_URL_POSTGRES]'
    const matches = detect(masked)
    const result = mask(masked, matches)
    assert.strictEqual(result, masked, 'masked text should not be re-masked')
  })

  test('multiple secrets in one string are all masked', () => {
    const text = [
      'AWS: AKIAIOSFODNN7EXAMPLE',
      'GH: ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890',
    ].join('\n')
    const matches = detect(text)
    assert.ok(matches.length >= 2, 'should detect both secrets')
    const result = mask(text, matches)
    assert.ok(!result.includes('AKIAIOSFODNN7EXAMPLE'), 'AWS key removed')
    assert.ok(!result.includes('ghp_'), 'GitHub PAT removed')
  })
})
