import * as assert from 'assert'
import { detect, mask } from '../../recognizers'

const CASES: { type: string; positive: string[]; negative: string[] }[] = [
  {
    type: 'AWS_ACCESS_KEY_ID',
    positive: ['AKIAIOSFODNN7EXAMPLE', 'token: AKIAIOSFODNN7EXAMPL2'],
    negative: ['BKIAIOSFODNN7EXAMPLE', 'AKIA12345'],
  },
  {
    type: 'GITHUB_PAT',
    positive: ['ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890'],
    negative: ['ghp_short', 'ghs_aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890'],
  },
  {
    type: 'GITHUB_APP_TOKEN',
    positive: ['ghs_aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890'],
    negative: ['ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890'],
  },
  {
    type: 'SLACK_BOT_TOKEN',
    positive: ['xoxb-12345678901-12345678901-aBcDeFgHiJkLmNoPqRsTuVwX'],
    negative: ['xoxb-short', 'xoxp-12345678901-12345678901-12345678901-aBcDeFgHiJkLmNoPqRsTuVwXyZ12345678'],
  },
  {
    type: 'SLACK_WEBHOOK',
    positive: ['https://hooks.slack.com/services/TXXXXXXXX/BXXXXXXXX/XXXXXXXXXXXXXXXXXXXXXXXX'],
    negative: ['https://api.slack.com/services/TXXXXXXXX'],
  },
  {
    type: 'STRIPE_SECRET_KEY',
    positive: ['sk_live_aBcDeFgHiJkLmNoPqRsTuVwX'],
    negative: ['sk_test_aBcDeFgHiJkLmNoPqRsTuVwX', 'sk_live_short'],
  },
  {
    type: 'STRIPE_TEST_KEY',
    positive: ['sk_test_aBcDeFgHiJkLmNoPqRsTuVwX'],
    negative: ['sk_live_aBcDeFgHiJkLmNoPqRsTuVwX'],
  },
  {
    type: 'SENDGRID_API_KEY',
    positive: ['SG.aBcDeFgHiJkLmNoPqRsTuV.aBcDeFgHiJkLmNoPqRsTuVwXyZ12345678901234567'],
    negative: ['SG.short.short'],
  },
  {
    type: 'TWILIO_ACCOUNT_SID',
    positive: ['AC1234567890abcdef1234567890abcdef'],
    negative: ['AC12345', 'BC1234567890abcdef1234567890abcdef'],
  },
  {
    type: 'GOOGLE_API_KEY',
    positive: ['AIzaSyC1234567890abcdefghijklmnopqrstuv'],
    negative: ['AIzaShort', 'BIzaSyC1234567890abcdefghijklmnopqrstu'],
  },
  {
    type: 'OPENAI_API_KEY',
    positive: ['sk-aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890abcdefghijkl'],
    negative: ['sk-short'],
  },
  {
    type: 'OPENAI_API_KEY_V2',
    positive: ['sk-proj-aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890abcdefghijklmnopqr'],
    negative: ['sk-proj-short'],
  },
  {
    type: 'NPM_TOKEN',
    positive: ['npm_aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890'],
    negative: ['npm_short'],
  },
  {
    type: 'SHOPIFY_ACCESS_TOKEN',
    positive: ['shpat_1234567890abcdef1234567890abcdef'],
    negative: ['shpat_short'],
  },
  {
    type: 'DATABASE_URL_POSTGRES',
    positive: ['postgresql://admin:s3cr3t@10.0.1.55:5432/prod_db'],
    negative: ['postgresql://localhost/nopassword'],
  },
  {
    type: 'DATABASE_URL_MONGODB',
    positive: ['mongodb+srv://user:pass@cluster0.example.com/db'],
    negative: ['mongodb://localhost/test'],
  },
  {
    type: 'PRIVATE_KEY_RSA',
    positive: ['-----BEGIN RSA PRIVATE KEY-----'],
    negative: ['-----BEGIN PUBLIC KEY-----'],
  },
  {
    type: 'PRIVATE_KEY_OPENSSH',
    positive: ['-----BEGIN OPENSSH PRIVATE KEY-----'],
    negative: ['-----END OPENSSH PRIVATE KEY-----'],
  },
  {
    type: 'JWT_TOKEN',
    positive: ['eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c'],
    negative: ['eyJshort.eyJshort.short'],
  },
  {
    type: 'PRIVATE_IP',
    positive: ['10.0.1.55', '192.168.1.100', '172.16.0.1'],
    negative: ['8.8.8.8', '256.256.256.256'],
  },
  {
    type: 'FIREBASE_URL',
    positive: ['https://my-app-default-rtdb.firebaseio.com'],
    negative: ['https://firebaseapp.com'],
  },
]

suite('recognizers', () => {
  for (const tc of CASES) {
    suite(tc.type, () => {
      for (const input of tc.positive) {
        test(`detects: ${input.slice(0, 40)}`, () => {
          const matches = detect(input)
          assert.ok(
            matches.some((m) => m.type === tc.type),
            `Expected ${tc.type} match in: ${input}`
          )
        })
      }
      for (const input of tc.negative) {
        test(`ignores: ${input.slice(0, 40)}`, () => {
          const matches = detect(input)
          assert.ok(
            !matches.some((m) => m.type === tc.type),
            `Did not expect ${tc.type} match in: ${input}`
          )
        })
      }
    })
  }

  suite('mask()', () => {
    test('replaces detected secrets with [REDACTED:TYPE]', () => {
      const text = 'postgresql://admin:s3cr3t@10.0.1.55:5432/prod_db'
      const matches = detect(text)
      const result = mask(text, matches)
      assert.ok(!result.includes('s3cr3t'), 'password should be redacted')
      assert.ok(result.includes('[REDACTED:'), 'should contain REDACTED marker')
    })

    test('returns original text when no secrets found', () => {
      const text = 'just a normal sentence with no secrets'
      const result = mask(text, detect(text))
      assert.strictEqual(result, text)
    })

    test('handles multiple secrets in one string', () => {
      const text = 'ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890 and AKIAIOSFODNN7EXAMPLE'
      const matches = detect(text)
      const result = mask(text, matches)
      assert.ok(!result.includes('ghp_'), 'GitHub PAT should be redacted')
      assert.ok(!result.includes('AKIA'), 'AWS key should be redacted')
    })
  })
})
