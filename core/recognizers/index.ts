export interface Match {
  type: string
  value: string
  start: number
  end: number
}

interface Pattern {
  type: string
  pattern: RegExp
  description: string
}

export const PATTERNS: Pattern[] = [
  // AWS
  { type: 'AWS_ACCESS_KEY_ID', pattern: /\bAKIA[A-Z0-9]{16}\b/g, description: 'AWS Access Key ID' },
  { type: 'AWS_SECRET_KEY', pattern: /(?:aws_secret_access_key|secret_key|secret_access_key)\s*[=:]\s*['"]?([A-Za-z0-9/+=]{40})/gi, description: 'AWS Secret Access Key (context-based)' },

  // GitHub
  { type: 'GITHUB_PAT', pattern: /\bghp_[A-Za-z0-9]{36}\b/g, description: 'GitHub personal access token (classic)' },
  { type: 'GITHUB_PAT_FINE', pattern: /\bgithub_pat_[A-Za-z0-9_]{82}\b/g, description: 'GitHub fine-grained PAT' },
  { type: 'GITHUB_APP_TOKEN', pattern: /\bghs_[A-Za-z0-9]{36}\b/g, description: 'GitHub App installation token' },
  { type: 'GITHUB_OAUTH_TOKEN', pattern: /\bgho_[A-Za-z0-9]{36}\b/g, description: 'GitHub OAuth token' },

  // Slack
  { type: 'SLACK_BOT_TOKEN', pattern: /\bxoxb-[0-9]{10,13}-[0-9]{10,13}-[A-Za-z0-9]{24}\b/g, description: 'Slack bot token' },
  { type: 'SLACK_USER_TOKEN', pattern: /\bxoxp-[0-9]{10,13}-[0-9]{10,13}-[0-9]{10,13}-[A-Za-z0-9]{32}\b/g, description: 'Slack user token' },
  { type: 'SLACK_APP_TOKEN', pattern: /\bxapp-\d-[A-Z0-9]{10,}-\d{11}-[A-Za-z0-9]{64}\b/g, description: 'Slack app-level token' },
  { type: 'SLACK_WEBHOOK', pattern: /https:\/\/hooks\.slack\.com\/services\/T[A-Z0-9]+\/B[A-Z0-9]+\/[A-Za-z0-9]+/g, description: 'Slack webhook URL' },

  // Stripe
  { type: 'STRIPE_SECRET_KEY', pattern: /\bsk_live_[A-Za-z0-9]{24,}\b/g, description: 'Stripe live secret key' },
  { type: 'STRIPE_TEST_KEY', pattern: /\bsk_test_[A-Za-z0-9]{24,}\b/g, description: 'Stripe test secret key' },
  { type: 'STRIPE_RESTRICTED_KEY', pattern: /\brk_live_[A-Za-z0-9]{24,}\b/g, description: 'Stripe restricted key' },

  // SendGrid
  { type: 'SENDGRID_API_KEY', pattern: /\bSG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}\b/g, description: 'SendGrid API key' },

  // Twilio
  { type: 'TWILIO_ACCOUNT_SID', pattern: /\bAC[a-f0-9]{32}\b/g, description: 'Twilio Account SID' },

  // Google
  { type: 'GOOGLE_API_KEY', pattern: /\bAIza[A-Za-z0-9_-]{35}\b/g, description: 'Google API key' },

  // OpenAI
  { type: 'OPENAI_API_KEY', pattern: /\bsk-[A-Za-z0-9]{48}\b/g, description: 'OpenAI API key (legacy)' },
  { type: 'OPENAI_API_KEY_V2', pattern: /\bsk-proj-[A-Za-z0-9_-]{48,}\b/g, description: 'OpenAI project API key' },

  // Anthropic
  { type: 'ANTHROPIC_API_KEY', pattern: /\bsk-ant-api\d{2}-[A-Za-z0-9_-]{93,}\b/g, description: 'Anthropic API key' },

  // NPM / PyPI
  { type: 'NPM_TOKEN', pattern: /\bnpm_[A-Za-z0-9]{36}\b/g, description: 'NPM access token' },
  { type: 'PYPI_TOKEN', pattern: /\bpypi-[A-Za-z0-9_-]{32,}\b/g, description: 'PyPI API token' },

  // Shopify
  { type: 'SHOPIFY_ACCESS_TOKEN', pattern: /\bshpat_[a-fA-F0-9]{32}\b/g, description: 'Shopify access token' },
  { type: 'SHOPIFY_CUSTOM_APP_TOKEN', pattern: /\bshpca_[a-fA-F0-9]{32}\b/g, description: 'Shopify custom app token' },

  // Mailchimp / Mailgun
  { type: 'MAILCHIMP_API_KEY', pattern: /\b[a-f0-9]{32}-us\d{1,2}\b/g, description: 'Mailchimp API key' },
  { type: 'MAILGUN_API_KEY', pattern: /\bkey-[a-z0-9]{32}\b/g, description: 'Mailgun API key' },

  // Database connection strings
  { type: 'DATABASE_URL_POSTGRES', pattern: /postgres(?:ql)?:\/\/[^:@\s]+:[^@\s]+@[^\s"']+/g, description: 'PostgreSQL connection string' },
  { type: 'DATABASE_URL_MYSQL', pattern: /mysql:\/\/[^:@\s]+:[^@\s]+@[^\s"']+/g, description: 'MySQL connection string' },
  { type: 'DATABASE_URL_MONGODB', pattern: /mongodb(?:\+srv)?:\/\/[^:@\s]+:[^@\s]+@[^\s"']+/g, description: 'MongoDB connection string' },
  { type: 'DATABASE_URL_REDIS', pattern: /redis(?:s)?:\/\/:[^@\s]+@[^\s"']+/g, description: 'Redis URL with password' },

  // Private keys
  { type: 'PRIVATE_KEY_RSA', pattern: /-----BEGIN RSA PRIVATE KEY-----/g, description: 'RSA private key' },
  { type: 'PRIVATE_KEY_EC', pattern: /-----BEGIN EC PRIVATE KEY-----/g, description: 'EC private key' },
  { type: 'PRIVATE_KEY_OPENSSH', pattern: /-----BEGIN OPENSSH PRIVATE KEY-----/g, description: 'OpenSSH private key' },
  { type: 'PRIVATE_KEY_PKCS8', pattern: /-----BEGIN PRIVATE KEY-----/g, description: 'PKCS#8 private key' },

  // JWT
  { type: 'JWT_TOKEN', pattern: /\beyJ[A-Za-z0-9+/=_-]{10,}\.[A-Za-z0-9+/=_-]{10,}\.[A-Za-z0-9+/=_-]{10,}\b/g, description: 'JSON Web Token' },

  // Generic URL with embedded credentials
  { type: 'URL_WITH_CREDENTIALS', pattern: /[a-zA-Z][a-zA-Z0-9+.-]*:\/\/[^:@\s]{1,100}:[^@\s]{3,100}@[^\s"']{1,200}/g, description: 'URL with embedded credentials' },

  // Private IP addresses
  { type: 'PRIVATE_IP', pattern: /\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b/g, description: 'Private IP address' },

  // Firebase
  { type: 'FIREBASE_URL', pattern: /https:\/\/[a-zA-Z0-9-]+\.firebaseio\.com/g, description: 'Firebase database URL' },

  // Azure
  { type: 'AZURE_STORAGE_CONNSTR', pattern: /DefaultEndpointsProtocol=https;AccountName=[^;]+;AccountKey=[A-Za-z0-9+/=]{86}/g, description: 'Azure storage connection string' },

  // Terraform Cloud
  { type: 'TERRAFORM_TOKEN', pattern: /\b[a-z0-9]{14}\.atlasv1\.[A-Za-z0-9]{60}\b/g, description: 'Terraform Cloud token' },

  // Docker Hub
  { type: 'DOCKER_HUB_PAT', pattern: /\bdop_v1_[a-f0-9]{64}\b/g, description: 'Docker Hub personal access token' },
]

export function detect(text: string): Match[] {
  const matches: Match[] = []
  for (const { type, pattern } of PATTERNS) {
    // Reset lastIndex — all patterns use /g flag
    pattern.lastIndex = 0
    let m: RegExpExecArray | null
    while ((m = pattern.exec(text)) !== null) {
      matches.push({ type, value: m[0], start: m.index, end: m.index + m[0].length })
    }
  }
  return deduplicateByPosition(matches)
}

export function mask(text: string, matches: Match[]): string {
  if (matches.length === 0) return text
  // Sort descending by start position so replacements don't shift indices
  const sorted = [...matches].sort((a, b) => b.start - a.start)
  let result = text
  for (const m of sorted) {
    result = result.slice(0, m.start) + `[REDACTED:${m.type}]` + result.slice(m.end)
  }
  return result
}

function deduplicateByPosition(matches: Match[]): Match[] {
  // When multiple patterns match the same span (e.g. URL_WITH_CREDENTIALS overlapping DATABASE_URL),
  // keep the more specific (longer type name / first encountered at that position).
  const seen = new Set<number>()
  return matches.filter((m) => {
    for (let i = m.start; i < m.end; i++) {
      if (seen.has(i)) return false
    }
    for (let i = m.start; i < m.end; i++) seen.add(i)
    return true
  })
}
