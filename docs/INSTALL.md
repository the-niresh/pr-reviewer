# Install

The installer never asks for hosted-plane credentials. Pairing uses a one-time browser or device code. Model keys are read with hidden input and stored in the OS secret store, or in `~/.config/pr-reviewer` mode `0600` when that store is missing.

## Install a versioned release

1. Download the release archive and its `SHA256SUMS` file.
2. Verify and copy it:

```sh
sh scripts/install.sh --archive pr-reviewer --checksum-file SHA256SUMS --prefix "$HOME/.local/bin"
```

The script copies the archive into the prefix only after `sha256sum -c` succeeds.

## Local versioned asset proof (2026-09-01)

A GitHub-hosted release asset is still unproven. Nothing was pushed and no
GitHub Release was created. That sub-step stays unfinished.

Local build and clean-container install on this machine:

```
$ sh scripts/build-local-release.sh /tmp/pr-reviewer-local-release
asset=/tmp/pr-reviewer-local-release/pr-reviewer-0.1.0-compose.release.yml
checksum_file=/tmp/pr-reviewer-local-release/SHA256SUMS
d1d71b483178c847dd9e4e359cfd548b4d85563c47c01e4b29e74246b2e67425  pr-reviewer-0.1.0-compose.release.yml
```

```
$ docker run --rm --user 65532:65532 \
    -v "$PWD/scripts/install.sh:/install.sh:ro" \
    -v /tmp/pr-reviewer-local-release/pr-reviewer-0.1.0-compose.release.yml:/pr-reviewer-0.1.0-compose.release.yml:ro \
    -v /tmp/pr-reviewer-local-release/SHA256SUMS:/SHA256SUMS:ro \
    busybox@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662 \
    sh /install.sh \
      --archive /pr-reviewer-0.1.0-compose.release.yml \
      --checksum-file /SHA256SUMS \
      --prefix /tmp/prefix
pr-reviewer-0.1.0-compose.release.yml: OK
```

Repeat in the same image after install: file size 1951 bytes, digest matches
`SHA256SUMS`. Exit code 0. No secrets in that output.

⬜ Install from a GitHub-hosted release URL. Blocked: nothing is pushed.

## Setup

```sh
reviewer setup --hosted-origin https://control.example.test
```

`--hosted-origin` is the public control-plane site. Hidden input collects the model key. Slack secrets, if used, are also hidden. The command rejects secret-bearing flags.

Then:

```sh
reviewer doctor
reviewer start --host 127.0.0.1
reviewer status
reviewer stop
```

`reviewer doctor` checks control-plane reachability, pairing, model keys, port use, disk space, and Docker. Full mode requires Docker. Analysis-only is offered only after its limits are shown.

## Uninstall

```sh
sh scripts/uninstall.sh
```

Data is kept by default. Deleting reviews and secrets needs both flags:

```sh
sh scripts/uninstall.sh --delete-data --confirm-delete
```
