# Git Command Guide

A practical summary of everyday Git commands: local work, remotes, deleting things, and changing commit messages.

---

## 1. Setup

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
git config --global init.defaultBranch main
git config --list                      # show current config
```

## 2. Starting a Repository

```bash
git init                               # new repo in current folder
git clone <url>                        # copy a remote repo locally
git clone <url> <folder>               # clone into a named folder
```

---

## 3. Local Workflow

### Check state

```bash
git status                             # what's changed
git diff                               # unstaged changes
git diff --staged                      # staged changes
git log --oneline --graph --decorate   # compact history
git log -p <file>                      # history of one file with diffs
git show <commit>                      # details of one commit
```

### Stage and commit

```bash
git add <file>                         # stage a file
git add .                              # stage everything
git add -p                             # stage interactively, hunk by hunk
git commit -m "Message"                # commit staged changes
git commit -am "Message"               # stage tracked files and commit
```

### Branches

```bash
git branch                             # list local branches
git branch -a                          # list local and remote branches
git switch <branch>                    # switch branch
git switch -c <new-branch>             # create and switch
git merge <branch>                     # merge branch into current one
git rebase <branch>                    # replay current branch on top of another
```

### Stash (temporarily shelve changes)

```bash
git stash                              # stash tracked changes
git stash -u                           # include untracked files
git stash list
git stash pop                          # re-apply and drop latest stash
git stash apply                        # re-apply but keep the stash
git stash drop                         # delete latest stash
```

---

## 4. Undoing Things Locally

| Goal | Command |
|---|---|
| Discard changes in a file | `git restore <file>` |
| Unstage a file (keep changes) | `git restore --staged <file>` |
| Undo last commit, keep changes staged | `git reset --soft HEAD~1` |
| Undo last commit, keep changes unstaged | `git reset --mixed HEAD~1` |
| Undo last commit and discard changes | `git reset --hard HEAD~1` |
| Create a new commit that reverses an old one | `git revert <commit>` |
| Remove untracked files (dry run first) | `git clean -n` then `git clean -f` |
| Recover "lost" commits | `git reflog` then `git reset --hard <hash>` |

> **Tip:** `git revert` is safe for shared history. `git reset` rewrites history, so avoid it on commits that are already pushed.

---

## 5. Deleting Things

### Local

```bash
git rm <file>                          # delete file and stage the deletion
git rm --cached <file>                 # stop tracking, keep file on disk
git branch -d <branch>                 # delete a merged branch
git branch -D <branch>                 # force-delete an unmerged branch
git tag -d <tag>                       # delete a local tag
git stash drop                         # delete a stash
```

### Remote

```bash
git push origin --delete <branch>      # delete a remote branch
git push origin --delete <tag>         # delete a remote tag
git push origin :refs/tags/<tag>       # older syntax for deleting a remote tag
git remote prune origin                # remove local refs to deleted remote branches
git fetch --prune                      # same idea, during a fetch
```

---

## 6. Changing Commit Messages

### Most recent commit (not yet pushed)

```bash
git commit --amend -m "New message"
```

Without `-m`, it opens your editor so you can rewrite the message.

You can also add forgotten files in the same step:

```bash
git add <file>
git commit --amend --no-edit           # keep the message, include the new file
```

### Most recent commit (already pushed)

```bash
git commit --amend -m "New message"
git push --force-with-lease
```

### An older commit (interactive rebase)

```bash
git rebase -i HEAD~3                   # edit the last 3 commits
```

1. In the editor, change `pick` to `reword` (or `r`) on the commit you want to change.
2. Save and close. Git will open the editor for each reworded commit.
3. Write the new message, save, and close.
4. If already pushed: `git push --force-with-lease`

Other useful rebase keywords: `squash` (combine into previous commit), `fixup` (squash and discard the message), `drop` (delete the commit), `edit` (pause to change the commit's contents).

> **Warning:** Amending or rebasing rewrites history. Only do this on commits that nobody else has based work on. Prefer `--force-with-lease` over `--force`, because it refuses to overwrite remote work you haven't seen.

---

## 7. Remotes

### Manage remotes

```bash
git remote -v                          # list remotes
git remote add origin <url>            # add a remote
git remote set-url origin <new-url>    # change a remote's URL
git remote rename origin upstream      # rename a remote
git remote remove <name>               # remove a remote
```

### Fetch, pull, push

```bash
git fetch                              # download changes, don't merge
git fetch --all --prune                # fetch every remote and clean stale refs
git pull                               # fetch and merge
git pull --rebase                      # fetch and rebase instead of merge
git push                               # push current branch
git push -u origin <branch>            # push and set upstream tracking
git push --force-with-lease            # safer force push after rewriting history
```

### Tracking branches

```bash
git branch -vv                         # show upstream for each branch
git branch -u origin/<branch>          # set upstream for current branch
git switch <branch>                    # auto-creates tracking branch if it exists on origin
```

---

## 8. Tags

```bash
git tag                                # list tags
git tag v1.0.0                         # lightweight tag
git tag -a v1.0.0 -m "Release 1.0.0"   # annotated tag (recommended for releases)
git tag -a v1.0.0 <commit>             # tag an older commit
git show v1.0.0                        # view tag details

git push origin v1.0.0                 # push one tag
git push origin --tags                 # push all tags

git tag -d v1.0.0                      # delete locally
git push origin --delete v1.0.0        # delete on remote
```

---

## 9. Handy Extras

```bash
git blame <file>                       # who changed each line
git cherry-pick <commit>               # copy a commit onto the current branch
git bisect start                       # binary search for the commit that broke something
git log --author="Name" --since="2 weeks ago"
git log --grep="keyword"               # search commit messages
git shortlog -sn                       # commit counts per author
git commit --amend --author="Name <email>"   # fix the author of the last commit
```

### Aliases worth setting

```bash
git config --global alias.st status
git config --global alias.co checkout
git config --global alias.lg "log --oneline --graph --decorate --all"
```

---

## 10. Quick Safety Rules

1. **Never rewrite shared history** (`reset`, `amend`, `rebase`) unless you've coordinated with your team.
2. **Use `--force-with-lease`**, not `--force`.
3. **Run `git status` and `git diff`** before committing.
4. **Use `git reflog`** if you think you've lost work. Most things are recoverable for a while.
5. **Dry-run destructive commands** where possible (`git clean -n`).
