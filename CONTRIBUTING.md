# Attaching Claude Code Transcripts to Pull Requests

This guide shows how to generate an HTML transcript of your Claude Code
session and attach it to a Pull Request so reviewers can see the full
conversation that produced the code.

## 1. Install

```bash
uv tool install claude-code-transcripts
```

Or run without installing:

```bash
uvx claude-code-transcripts --help
```

## 2. Generate HTML

### Interactive picker (local sessions)

```bash
claude-code-transcripts
```

This lists your recent Claude Code sessions, lets you pick one, and opens
the rendered HTML in your browser.

### From a specific session file

```bash
claude-code-transcripts json ~/.claude/projects/.../session.jsonl \
  -o ./transcript/
```

### With GitHub repo links

Add `--repo owner/name` so commit hashes in the transcript link to GitHub:

```bash
claude-code-transcripts json session.jsonl \
  -o ./transcript/ --repo myorg/myrepo
```

The repo is auto-detected from `git push` output when possible.

## 3. Attach to a PR

### Option A: GitHub Pages (recommended)

Host the HTML on GitHub Pages so the transcript is fully interactive
(sidebar navigation, user-only filter, scroll tracking all work).

```bash
# Generate the transcript
claude-code-transcripts json session.jsonl -o ./transcript/

# Create a gh-pages branch with the HTML
git stash
git checkout --orphan gh-pages
git rm -rf .
cp transcript/index.html transcript.html
git add transcript.html
git commit -m "Add session transcript"
git push origin gh-pages
git checkout -            # back to your feature branch
git stash pop
```

Enable GitHub Pages in your repo settings (source: `gh-pages` branch), or
use the API:

```bash
gh api repos/OWNER/REPO/pages --method POST \
  --field source='{"branch":"gh-pages","path":"/"}'
```

Then link it in your PR:

```
[View Claude session transcript](https://OWNER.github.io/REPO/transcript.html)
```

### Option B: GitHub Gist

Quick and simple, but JavaScript features (FAB button, sidebar nav) are
sandboxed and won't run.

```bash
claude-code-transcripts json session.jsonl --gist
```

This uploads the HTML to a public Gist and prints the URL. Paste the URL
in your PR description.

### Option C: Screenshots + local file

If you don't need hosting, open the HTML locally and screenshot it:

```bash
cd transcript/
python3 -m http.server 8000
# Open http://localhost:8000 in your browser
# Take screenshots, drag them into the PR comment on GitHub
```

## 4. End-to-end example

```bash
# Work on your feature
git checkout -b add-auth-flow

# ... make changes with Claude Code ...
# Claude Code saves the session to ~/.claude/projects/.../<session-id>.jsonl

# Generate transcript with repo links
claude-code-transcripts json \
  ~/.claude/projects/-path-to-project/<session-id>.jsonl \
  -o ./transcript/ --repo myorg/myrepo

# Host on GitHub Pages
git stash
git checkout --orphan gh-pages
git rm -rf .
cp transcript/index.html auth-flow-transcript.html
git add auth-flow-transcript.html
git commit -m "Add auth flow transcript"
git push origin gh-pages
git checkout add-auth-flow
git stash pop

# Push your feature branch and open the PR
git push -u origin add-auth-flow
gh pr create \
  --title "Add authentication flow" \
  --body "## Summary
Implements OAuth2 login flow.

## Claude Code transcript
[View full session](https://myorg.github.io/myrepo/auth-flow-transcript.html)

## Test plan
- [ ] Login with Google
- [ ] Login with GitHub
- [ ] Token refresh works"
```

## Tips

- **Multiple transcripts**: add each as a separate `.html` file on the
  `gh-pages` branch.
- **Batch export**: use `claude-code-transcripts all -o ./archive/` to
  convert every local session at once.
- **Include raw JSONL**: add `--json` to save the original session file
  alongside the HTML.
- **Session titles**: the generated HTML uses your first message as the
  page title, so start with a clear description of what you're doing.
