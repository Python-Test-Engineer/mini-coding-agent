# Hermes Agent: OpenRouter API Key (PowerShell)

CLAUDE

$env:ANTHROPIC_API_KEY = <"API-KEY>"

OPENAI

$env:OPENAI_API_KEY = "sk-..." 
setx OPENAI_API_KEY "sk-..."

## Quick reference

```powershell
hermes config                                   # view config
hermes config edit                              # edit config.yaml
hermes config set OPENROUTER_API_KEY sk-or-...  # set/replace key (saves to .env)
hermes model                                    # interactive provider/model setup
hermes config check                             # check for missing options
```

How to **see** the current OpenRouter key, **delete all references** to it, and **set up a new one** on Windows.

Hermes keeps secrets in `.env` and settings in `config.yaml`. The folder is usually `%USERPROFILE%\.hermes\`, but some setups use `%LOCALAPPDATA%\hermes\`. The commands below check both.

---

## 1. See the current key

```powershell
# Find where Hermes keeps its files
$paths = "$env:USERPROFILE\.hermes\.env", "$env:LOCALAPPDATA\hermes\.env"
$paths | Where-Object { Test-Path $_ }

# Show the key line (masked)
Get-Content $paths -ErrorAction SilentlyContinue |
  Where-Object { $_ -match '^OPENROUTER_API_KEY=' } |
  ForEach-Object { $_ -replace '(sk-or-.{6}).*(.{4})$', '$1...$2' }

# Show the full key (only if needed)
Select-String -Path $paths -Pattern 'OPENROUTER_API_KEY' -ErrorAction SilentlyContinue

# Check for overriding environment variables
$env:OPENROUTER_API_KEY
[Environment]::GetEnvironmentVariable("OPENROUTER_API_KEY", "User")
[Environment]::GetEnvironmentVariable("OPENROUTER_API_KEY", "Machine")

# Hermes's own view
hermes config
```

To confirm which key OpenRouter sees, compare the last 4 characters at https://openrouter.ai/keys.

---

## 2. Delete all references

**Revoke the old key first** at https://openrouter.ai/keys, so it is dead even if a copy is missed.

```powershell
# Back up and remove the line from each .env
foreach ($f in $paths) {
  if (Test-Path $f) {
    Copy-Item $f "$f.bak"
    (Get-Content $f) | Where-Object { $_ -notmatch '^OPENROUTER_API_KEY=' } | Set-Content $f
  }
}

# Remove environment variables (Machine needs an admin PowerShell)
[Environment]::SetEnvironmentVariable("OPENROUTER_API_KEY", $null, "User")
[Environment]::SetEnvironmentVariable("OPENROUTER_API_KEY", $null, "Machine")
Remove-Item Env:OPENROUTER_API_KEY -ErrorAction SilentlyContinue

# Check config.yaml for pasted keys (delete any sk-or-... or api_key lines)
hermes config edit
```

### Hunt down leftover copies

```powershell
# Add your own project folders to $roots
$roots = "$env:USERPROFILE\.hermes", "$env:LOCALAPPDATA\hermes", "C:\path\to\your\projects"

Get-ChildItem -Path $roots -Recurse -File -Force -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -notmatch '\\(node_modules|\.git|venv|\.venv)\\' } |
  Select-String -Pattern 'sk-or-', 'OPENROUTER_API_KEY' -List |
  Select-Object Path

# PowerShell history
Select-String -Path (Get-PSReadLineOption).HistorySavePath -Pattern 'sk-or-'
```

If the history search finds anything, delete those lines from the file, or clear the whole history:

```powershell
Remove-Item (Get-PSReadLineOption).HistorySavePath
```

Common hiding places:
- Project `.env` files (e.g. `vendor\hermes-agent-framework\.env`)
- `.env.bak` and `.env.example` files you edited
- Docker/compose files and CI secrets
- Python scripts or notebooks with hardcoded keys
- Hermes session logs if you ever pasted the key into a chat
- Git history (if committed, treat as leaked; revoking handles it)

---

## 3. Set the new key

Create it at https://openrouter.ai/keys. Name it something identifiable and consider setting a credit limit.

```powershell
# Easiest: Hermes writes it to .env for you
hermes config set OPENROUTER_API_KEY sk-or-v1-xxxxxxxx

# Or interactive setup (provider and model too, keeps the key out of history)
hermes model

# Or manually
Add-Content "$env:USERPROFILE\.hermes\.env" "OPENROUTER_API_KEY=sk-or-v1-xxxxxxxx"

# Test
hermes chat --provider openrouter --model '~anthropic/claude-sonnet-latest'
```

Open a **new** PowerShell window afterwards so no stale environment variable lingers, then check https://openrouter.ai/activity to confirm requests are using the new key.

> **Note:** Typing the key into `hermes config set ...` saves it in plain text in your PowerShell history. Delete that history line afterwards, or use `hermes model` instead.

---

## 4. Verify clean

```powershell
Get-ChildItem $roots -Recurse -File -Force -ErrorAction SilentlyContinue |
  Select-String -Pattern 'sk-or-' -List | Select-Object Path
```

You should only see the `.env` file holding the **new** key.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Hermes can't find the key | `Select-String -Path $paths -Pattern OPENROUTER`, then re-run `hermes config set OPENROUTER_API_KEY ...` or `hermes model` |
| Old key still used | An environment variable or project-local `.env` is overriding it. Repeat section 2 and open a new window |
| 401 invalid key | Key revoked or mistyped. Check for trailing spaces or quotes in `.env` |
| 402 insufficient credits | Top up at https://openrouter.ai/credits or raise the key's limit |
| Context errors | Hermes needs a model with at least 64K context |

## Quick reference

```powershell
hermes config                                   # view config
hermes config edit                              # edit config.yaml
hermes config set OPENROUTER_API_KEY sk-or-...  # set/replace key (saves to .env)
hermes model                                    # interactive provider/model setup
hermes config check                             # check for missing options
```

Docs: https://hermes-agent.nousresearch.com/docs
