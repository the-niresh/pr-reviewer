# Install

The installer never asks for hosted-plane credentials. Pairing uses a one-time browser or device code. Model keys are read with hidden input and stored in the OS secret store, or in `~/.config/pr-reviewer` mode `0600` when that store is missing.

## Install a versioned release

1. Download the release archive and its `SHA256SUMS` file.
2. Verify and copy it:

```sh
sh scripts/install.sh --archive pr-reviewer --checksum-file SHA256SUMS --prefix "$HOME/.local/bin"
```

The script copies the archive into the prefix only after `sha256sum -c` succeeds.

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
