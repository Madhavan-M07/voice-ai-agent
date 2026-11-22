#!/usr/bin/env node
// PreToolUse guard for Bash/PowerShell commands.
//   DENY  -> exit 2, reason on stderr (Claude sees it and must change course)
//   ASK   -> JSON permissionDecision "ask" (user confirms in the UI)
//   else  -> exit 0 (normal permission rules apply)
// Add project-specific rules to the two tables below.

const DENY = [
  [/\brm\s+-\w*(rf|fr)\w*\s+(\/|~\/?|\*|\.\/?|\$HOME\/?)(\s|$)/i, 'Recursive force-delete of root/home/cwd'],
  [/Remove-Item\b.*-Recurse\b.*\s([A-Z]:\\?|~|\$HOME|\.)(\s|$)/i, 'Recursive delete of a drive root/home/cwd'],
  [/\b(curl|wget|iwr|Invoke-WebRequest)\b[^|]*\|\s*(sudo\s+)?(sh|bash|zsh|iex|Invoke-Expression|python)\b/i, 'Piping a remote script into a shell'],
  [/\bgit\s+push\b.*\s(--force(?![-\w])|-f)(\s|$).*\b(main|master|production|release)\b/, 'Force-push to a protected branch'],
  [/\bgit\s+push\b.*\b(main|master|production|release)\b.*\s(--force(?![-\w])|-f)(\s|$)/, 'Force-push to a protected branch'],
  [/\bmkfs\b|\bdd\s+.*of=\/dev\/|:\(\)\s*\{\s*:\|:&\s*\};:/, 'Destructive disk/system command'],
  [/\bchmod\s+-R\s+777\s+\//, 'chmod -R 777 on root'],
  [/\b(cat|type|Get-Content|less|more|head|tail)\b[^|;&]*(^|[\s\/\\])\.env(\s|$)/i, 'Reading .env secrets — use .env.example'],
];

const ASK = [
  [/\bgit\s+push\b.*\s(--force|--force-with-lease|-f)(\s|$|=)/, 'Force-push rewrites remote history'],
  [/\bgit\s+reset\s+--hard\b/, 'git reset --hard discards uncommitted work'],
  [/\bgit\s+clean\s+-\w*f/, 'git clean deletes untracked files'],
  [/\bgit\s+(checkout|restore)\s+(--\s+)?\.(\s|$)/, 'Discards all working-tree changes'],
  [/\bgit\s+branch\s+-D\b/, 'Force-deletes a branch'],
  [/\b(DROP|TRUNCATE)\s+(TABLE|DATABASE|SCHEMA)\b/i, 'Destructive SQL'],
  [/\bterraform\s+(apply|destroy)\b|\bkubectl\s+(delete|apply)\b|\bhelm\s+(uninstall|upgrade)\b/, 'Infrastructure change'],
  [/\b(npm|pnpm|yarn)\s+publish\b|\btwine\s+upload\b|\bcargo\s+publish\b/, 'Publishing a package'],
  [/\brm\s+-\w*r/, 'Recursive delete'],
];

let raw = '';
process.stdin.on('data', (c) => (raw += c));
process.stdin.on('end', () => {
  let cmd = '';
  try {
    cmd = (JSON.parse(raw).tool_input || {}).command || '';
  } catch {
    process.exit(0);
  }

  for (const [re, why] of DENY) {
    if (re.test(cmd)) {
      process.stderr.write(`Blocked by .claude/hooks/guard-shell.js: ${why}.\nCommand: ${cmd}\nFind a safer approach or ask the user to run it themselves.`);
      process.exit(2);
    }
  }
  for (const [re, why] of ASK) {
    if (re.test(cmd)) {
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: {
          hookEventName: 'PreToolUse',
          permissionDecision: 'ask',
          permissionDecisionReason: `Guard: ${why}`,
        },
      }));
      process.exit(0);
    }
  }
  process.exit(0);
});
