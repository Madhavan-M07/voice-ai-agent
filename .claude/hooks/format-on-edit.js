#!/usr/bin/env node
// PostToolUse: auto-format the Python file Claude just edited with the project's own ruff
// (from the nearest pyproject's .venv, so it works without ruff on PATH). Silent no-op when
// no formatter is found. Never blocks.

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const isWin = process.platform === 'win32';

// Walk up from the edited file to the folder holding pyproject.toml (e.g. backend/).
function findProjectRoot(file) {
  let dir = path.dirname(path.resolve(file));
  while (true) {
    if (fs.existsSync(path.join(dir, 'pyproject.toml'))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

function findRuff(root) {
  const venvRuff = path.join(root, '.venv', isWin ? 'Scripts' : 'bin', isWin ? 'ruff.exe' : 'ruff');
  if (fs.existsSync(venvRuff)) return venvRuff;
  const onPath = spawnSync(isWin ? 'where' : 'which', ['ruff'], { stdio: 'ignore', shell: isWin });
  return onPath.status === 0 ? 'ruff' : null;
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
  if (!file || path.extname(file).toLowerCase() !== '.py' || !fs.existsSync(file)) process.exit(0);

  const root = findProjectRoot(file);
  const ruff = root && findRuff(root);
  if (!ruff) process.exit(0);

  // cwd = project root so ruff picks up [tool.ruff] from pyproject.toml.
  const opts = { cwd: root, stdio: 'ignore', timeout: 30000 };
  spawnSync(ruff, ['format', '--quiet', file], opts);
  spawnSync(ruff, ['check', '--fix', '--quiet', file], opts);
  process.exit(0);
});
