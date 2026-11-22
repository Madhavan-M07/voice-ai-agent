#!/usr/bin/env node
// PostToolUse: auto-format the file Claude just edited, using whichever formatter
// the project actually has. Silent no-op when no formatter is available. Never blocks.

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const projectDir = process.env.CLAUDE_PROJECT_DIR || process.cwd();
const isWin = process.platform === 'win32';

function onPath(bin) {
  const r = spawnSync(isWin ? 'where' : 'which', [bin], { stdio: 'ignore', shell: isWin });
  return r.status === 0;
}
function localBin(name) {
  const p = path.join(projectDir, 'node_modules', '.bin', isWin ? `${name}.cmd` : name);
  return fs.existsSync(p) ? p : null;
}
function run(cmd, args) {
  spawnSync(isWin ? `"${cmd}"` : cmd, args.map((a) => (isWin ? `"${a}"` : a)), {
    cwd: projectDir, stdio: 'ignore', shell: isWin, timeout: 50000,
  });
}

let raw = '';
process.stdin.on('data', (c) => (raw += c));
process.stdin.on('end', () => {
  let file = '';
  try {
    file = (JSON.parse(raw).tool_input || {}).file_path || '';
  } catch {
    process.exit(0);
  }
  if (!file || !fs.existsSync(file)) process.exit(0);

  const ext = path.extname(file).toLowerCase();
  try {
    if (['.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.json', '.css', '.scss', '.html', '.vue', '.svelte', '.yaml', '.yml'].includes(ext)) {
      const prettier = localBin('prettier');
      if (prettier) run(prettier, ['--write', '--log-level', 'silent', file]);
    } else if (ext === '.py') {
      if (onPath('ruff')) { run('ruff', ['format', '--quiet', file]); run('ruff', ['check', '--fix', '--quiet', file]); }
      else if (onPath('black')) run('black', ['-q', file]);
    } else if (ext === '.go') {
      if (onPath('gofmt')) run('gofmt', ['-w', file]);
    } else if (ext === '.rs') {
      if (onPath('rustfmt')) run('rustfmt', [file]);
    }
  } catch {
    /* formatting is best-effort */
  }
  process.exit(0);
});
