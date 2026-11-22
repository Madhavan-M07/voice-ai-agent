#!/usr/bin/env node
// SessionStart: anything printed to stdout is added to Claude's context.
// Gives Claude the current branch, uncommitted changes and recent commits up front.

const { execSync } = require('child_process');
const cwd = process.env.CLAUDE_PROJECT_DIR || process.cwd();
const git = (args) => {
  try {
    return execSync(`git ${args}`, { cwd, stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
  } catch {
    return null;
  }
};

if (git('rev-parse --is-inside-work-tree') !== 'true') {
  console.log('Session context: not a git repository yet.');
  process.exit(0);
}

const branch = git('branch --show-current') || '(detached)';
const status = git('status --short') || '(clean)';
const log = git('log --oneline -8') || '(no commits yet)';

console.log(`Session context
Branch: ${branch}
Uncommitted changes:
${status.split('\n').slice(0, 30).join('\n')}
Recent commits:
${log}`);
