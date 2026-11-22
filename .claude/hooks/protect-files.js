#!/usr/bin/env node
// PreToolUse guard for Edit/Write: blocks edits to secrets, lockfiles and VCS internals.
// Exit 2 = block; the stderr message is shown to Claude.

const path = require('path');

const RULES = [
  [/(^|[\\/])\.env(\.(?!example$|sample$|template$)[^\\/]+)?$/i, 'Secrets file (.env). Edit .env.example instead and tell the user which real values to set.'],
  [/\.(pem|key|p12|pfx|crt|keystore|jks)$/i, 'Key/certificate material.'],
  [/(^|[\\/])(id_rsa|id_ed25519)(\.pub)?$/i, 'SSH key.'],
  [/(^|[\\/])secrets?[\\/]/i, 'Secrets directory.'],
  [/(^|[\\/])(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|bun\.lockb?|poetry\.lock|uv\.lock|Pipfile\.lock|Cargo\.lock|go\.sum|composer\.lock|Gemfile\.lock)$/, 'Lockfile — change it through the package manager, not by hand.'],
  [/(^|[\\/])\.git[\\/]/, 'Git internals.'],
];

let raw = '';
process.stdin.on('data', (c) => (raw += c));
process.stdin.on('end', () => {
  let file = '';
  try {
    const input = JSON.parse(raw).tool_input || {};
    file = input.file_path || input.notebook_path || input.path || '';
  } catch {
    process.exit(0);
  }
  if (!file) process.exit(0);

  const normalized = file.split(path.sep).join('/');
  for (const [re, why] of RULES) {
    if (re.test(normalized)) {
      process.stderr.write(`Blocked by .claude/hooks/protect-files.js: ${why}\nFile: ${file}`);
      process.exit(2);
    }
  }
  process.exit(0);
});
