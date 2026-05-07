import * as assert from 'assert'
import { SIDECAR_PORT, AIVION_DIR } from '../../sidecar'
import * as os from 'os'
import * as path from 'path'

suite('Sidecar constants', () => {
  test('port is 47474', () => {
    assert.strictEqual(SIDECAR_PORT, 47474)
  })

  test('AIVION_DIR is in home directory', () => {
    assert.strictEqual(AIVION_DIR, path.join(os.homedir(), '.aivion-mask'))
  })
})
