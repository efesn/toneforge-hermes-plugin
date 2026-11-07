# Catalog PR — exact steps

The PR adds **one file** to `NousResearch/hermes-agent`:

```
plugin-catalog/tone-forge.yaml
```

The file is ready at [`catalog-entry.yaml`](catalog-entry.yaml) in this folder. Pin it to a
commit that is **already pushed** (the entry currently pins `3207e75`, which is on
`origin/main`).

## Commands (run from this repo)

```bash
# 1. Work against your own copy of hermes-agent
gh repo fork NousResearch/hermes-agent --clone --remote   # once; or use the web fork button
cd hermes-agent
git checkout -b add-tone-forge-plugin

# 2. Add the entry
cp <path-to-toneforge-repo>/hackathon/catalog-entry.yaml plugin-catalog/tone-forge.yaml

# 3. Validate the entry shape the way catalog CI will
python -c "import yaml,sys; d=yaml.safe_load(open('plugin-catalog/tone-forge.yaml')); \
print(d['name'], d['version'], len(d['sha']), len(d['capabilities']['provides_tools']))"

# 4. Commit + push to your fork
git add plugin-catalog/tone-forge.yaml
git commit -m "Add tone-forge to the plugin catalog"
git push -u origin add-tone-forge-plugin

# 5. Open the PR against NousResearch/hermes-agent:main
gh pr create --repo NousResearch/hermes-agent --base main \
  --title "Add tone-forge plugin" --body-file <path-to>/hackathon/pr-body.md
```

No `gh`? Use the GitHub web UI after step 4 — GitHub prints a "Compare & pull request"
banner for the pushed branch.

## PR body

Use [`pr-body.md`](pr-body.md). It states what the plugin does, which Hermes surfaces it uses
(`ctx.register_tool`, `config_schema`) and the rule-13 disclosure the reviewers look for.

## What the reviewer will check

- **Exact SHA pin** — 40 characters, commit must exist publicly. If you push new commits,
  re-pin and say so in the PR.
- **Catalog CI** clones the repo at the pinned SHA and runs `hermes plugins validate`.
  Locally that is already passing on this machine.
- **Declared tools match registrations** — the entry lists 17, which is what
  `register(ctx)` registers.
- **Disclosure** — the subprocess/network path (`ffmpeg`, `yt-dlp` for explicit URLs) is
  described in the entry `description`, as rule 13 requires.
