# Working with git: one branch per issue

This is how we take an issue from the board to `main`. It is the "GitHub flow" that most teams
use: `main` always works, every change happens on its own branch, and a pull request is reviewed
before it is merged.

```
main ──●────────────●──────────────●──   (always works, always deployable)
        \          /                /
         ●──●──●──●   007-...      /     (your feature branch: small commits)
                     \            /
                      ●───●───●──●       (someone else's branch, at the same time)
```

## Once: set up git

```sh
git config --global user.name "Your Name"
git config --global user.email "you@example.com"     # the email of your GitHub account
git config --global init.defaultBranch main
git config --global pull.rebase false                 # `git pull` merges; simplest to start
git config core.hooksPath .githooks                   # in this repo: run the checks before each commit
```

On Windows, use Git Bash (it comes with [Git for Windows](https://gitforwindows.org/)).

## The loop, for every issue

### 1. Pick an issue and start from a fresh `main`

Pick a card from `# todo` in `issues/_kanban.md` whose "Depends on" issues are all done. Tell the
others you're taking it (chat, or the class board), so two people don't build the same thing.

```sh
git switch main
git pull                                  # get everyone's merged work
git switch -c 007-registration-windows    # a new branch, named like the issue file
```

### 2. Work in small commits

Commit whenever one small step works: a model, its migration, a view with its test. A commit is
a save point you can go back to, and a message that explains the change to your classmates.

```sh
git status                    # what changed?
git diff                      # the changes themselves
git add accounts/models.py accounts/migrations/0002_registrationwindow.py
git commit -m "Add the RegistrationWindow model"
```

Good commit messages are short and say what the commit does, as an order: "Add …", "Fix …",
"Remove …", "Show …". Not "changes", "wip" or "fixed stuff".

The pre-commit hook runs `scripts/check.sh`. If it fails, the commit is refused: read the error,
fix it, `git add` again and commit again. Don't skip the hook (`--no-verify`): the same checks
run on every pull request anyway.

### 3. Push and open a pull request

```sh
git push -u origin 007-registration-windows    # the first time; later just `git push`
```

GitHub prints a link: open it and create the pull request (PR).
- **Title:** the issue's title.
- **Description:** "Closes issue 007", what you did, anything the reviewer should look at
  closely, and screenshots for screen changes.

### 4. Review

A classmate (or the teacher) reads the PR and leaves comments. Reviewing is half the learning:
read other people's PRs too, and ask questions. You can also ask an AI agent for a first review
(AGENTS.md, Subagents).

Fix what the review asks for with new commits on the same branch and push again; the PR updates
itself.

### 5. Merge and clean up

When the PR is approved and `scripts/check.sh` passes, merge it on GitHub with **Create a merge
commit**, titled `Merge 007: <summary>`. Then:

```sh
git switch main
git pull
git branch -d 007-registration-windows      # delete your local branch
```

Whoever merged moves the card to `# done` in `issues/_kanban.md`, in a small commit on `main`.
Branches never touch the board, so two PRs don't conflict there.

Then deploy (`docs/deployment/deploy-to-dokku.md`, part 13).

## When `main` moved on while you worked

Bring the new `main` into your branch before you open (or merge) the PR:

```sh
git switch main && git pull
git switch 007-registration-windows
git merge main
```

If git says **CONFLICT**, two people changed the same lines. Open each file it names, look for the
markers, keep what is right (often both changes), and delete the markers:

```
<<<<<<< HEAD
your version
=======
the version from main
>>>>>>> main
```

Then `git add` the files, `git commit`, and run `scripts/check.sh`. Two migrations with the same
number in one app are a special case: run `uv run python manage.py makemigrations --merge`.

## Undo, safely

| You want to… | Command |
|---|---|
| throw away changes to a file you haven't committed | `git restore <file>` |
| unstage a file you added by mistake | `git restore --staged <file>` |
| fix the message of your last commit (not pushed yet) | `git commit --amend` |
| undo a commit that is already pushed | `git revert <commit>` (a new commit that undoes it) |
| see what happened | `git log --oneline --graph --all` |

Never `git push --force` to `main`.

## Further reading

- [Pro Git](https://git-scm.com/book/en/v2), free online: chapters 2 (basics) and 3 (branching).
- [GitHub flow](https://docs.github.com/en/get-started/using-github/github-flow): the workflow
  above, by GitHub.
- [About pull requests](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-pull-requests)
  and [reviewing changes in pull requests](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests).
- [How to write a git commit message](https://cbea.ms/git-commit/), by Chris Beams.
- [Oh Shit, Git!?!](https://ohshitgit.com/): getting out of common messes.
- [Learn Git Branching](https://learngitbranching.js.org/): an interactive visual tutorial.
