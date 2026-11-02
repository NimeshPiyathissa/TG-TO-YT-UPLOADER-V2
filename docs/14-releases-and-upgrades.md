# 14. Releases, updates and rollbacks

How versions are numbered, how a server gets a new version, and how to go back if something is wrong.

## Versions

- The version is in the `VERSION` file and follows [Semantic Versioning](https://semver.org): `MAJOR.MINOR.PATCH`.
  A patch release (`1.0.1`) only fixes things; a minor release adds features without breaking settings; a major release may need manual steps,
  which its changelog entry spells out.
- Every release is a Git tag `vX.Y.Z` on `main`, with its notes in [CHANGELOG.md](../CHANGELOG.md).
- `tgyt status` and the `tgyt update` summary show the installed version.

## Updating a server

```bash
sudo tgyt update                   # newest STABLE release: lists the changes, asks, then upgrades
sudo tgyt update --ref v1.0.1      # a specific tag (or branch/commit); also the only way to install a pre-release such as v1.1.0-rc.1
sudo tgyt update -y                # don't ask (for scripts)
sudo tgyt update --from /path/to/unpacked/source    # install from a folder instead of Git (offline or private copies)
```

**Which version is "newest stable":** for a GitHub repository, the one GitHub calls the latest release. GitHub never counts
pre-releases or drafts, so a pre-release is not installed even if its tag looks stable (`v1.0.1`). For other Git hosts, the highest plain
`vX.Y.Z` tag (`-rc`, `-beta` tags are skipped). If GitHub can't be reached, nothing changes; if no stable release exists yet, nothing
changes; and a server already running something newer (e.g. a pre-release installed with `--ref`) is never downgraded.

What `tgyt update` does, in order:

1. gets the new source (Git fetch in `/opt/tgyt-src`, or the folder given with `--from`);
2. saves a **rollback copy** in `/opt/tgyt-rollback/<date-time>`: code, Python environment, database and keys;
3. stops the service, installs the new code, updates the pinned Python packages and **migrates the database**;
4. starts the service and watches it for about 1.5 minutes (running, no restarts, panel answers, no fatal errors in the log);
5. if any step or the health check fails, it **rolls back automatically** to the copy from step 2.

Your settings (`/etc/tgyt/tgyt.env`), the Fernet key, the database contents and the off-site backup configuration are kept.

**Before updating:** check nothing is uploading (`/jobs`, or the panel dashboard). The update restarts the service; interrupted transfers
resume afterwards, but it's simpler to wait. If the release notes say the web server config changed, also run
`sudo /opt/tgyt-uploader/deploy/install.sh` and choose *Keep my settings*.

## Rolling back

```bash
sudo tgyt rollback       # restores the code AND the database from the last rollback copy (asks first)
```

The database goes back to the moment of the update, so anything done since (new channels, finished jobs) is undone. To keep current data and
only change the code, install the older version instead: `sudo tgyt update --ref vX.Y.Z` (the tag you want).

## If the repository is private

The one-line installer, `git clone` and `tgyt update` all download from GitHub. For a **private** repository the server needs read access;
anonymous downloads fail with *Could not download* / *Could not reach the repository*. Two ways:

**A. Read-only deploy key (recommended for servers):**

```bash
sudo ssh-keygen -t ed25519 -N "" -f /root/.ssh/tgyt_repo -C "tgyt server read-only"
sudo cat /root/.ssh/tgyt_repo.pub
# GitHub → the repository → Settings → Deploy keys → Add deploy key → paste it, leave "Allow write access" OFF
printf 'Host github.com\n  IdentityFile /root/.ssh/tgyt_repo\n  IdentitiesOnly yes\n' | sudo tee -a /root/.ssh/config
sudo ssh -T git@github.com            # answer "yes" once; expect "successfully authenticated"
sudo git clone git@github.com:NimeshPiyathissa/TG-TO-YT-UPLOADER-V2.git /root/tgyt-install
sudo /root/tgyt-install/install.sh             # works from any folder: the installer finds itself
```

The installer copies that checkout, including its SSH `origin`, to `/opt/tgyt-src`; `tgyt update` runs as root and fetches with the same key,
so updates keep working.

**B. No Git access on the server:** download or copy the release to the server (for example a `.tar` made with
`git -c core.autocrlf=false archive --format=tar vX.Y.Z`), unpack it, and run `sudo ./install.sh` from that folder for a new install, or
`sudo tgyt update --from /path/to/folder` for an update.

## Making a release (maintainers)

1. All changes merged to `main`; CI green (tests, ShellCheck, secret scan).
2. Bump `VERSION`; in `CHANGELOG.md` rename *Unreleased* to `[X.Y.Z] — YYYY-MM-DD` and start a new empty *Unreleased*.
3. Test the release on a **non-production** server: a fresh install, `tgyt doctor`, a real upload, `tgyt backup` + `tgyt offsite restore-test`,
   `tgyt update` from the previous version, `tgyt rollback`.
4. Tag and push: `git tag -a vX.Y.Z -m "vX.Y.Z" && git push origin vX.Y.Z`.
5. Create the GitHub release from the tag with the changelog section as notes.
6. Update production with `sudo tgyt update --ref vX.Y.Z` when nothing is uploading, then `tgyt doctor` and `tgyt offsite restore-test`.
