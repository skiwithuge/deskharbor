# DeskHarbor

<img src="assets/deskharbor-icon.png" alt="DeskHarbor lighthouse" width="160">

**Your workstation, wherever you dock.**

A persistent, GPU-ready Linux workstation in Docker. Access your desktop, audio, and development tools from different devices while keeping your applications and settings in one place.

DeskHarbor is for a Linux x86-64 Docker host. The thin client can be Linux, macOS, Windows or a phone. CPU mode works without NVIDIA; the optional GPU mode adds a CUDA development image and requires working host NVIDIA drivers and NVIDIA Container Toolkit. Desktop rendering uses software graphics; CUDA compute support does not imply accelerated desktop OpenGL.

## Start here

Install Docker Engine with the Compose v2 plugin, Python 3 (including curses), and OpenSSH client tools on your **host**. Docker must be usable by your normal account. DeskHarbor checks prerequisites; it does not silently install drivers or modify host security policies.

```bash
./deskharbor
```

The host TUI offers First setup / Configuration, Start / apply, Status, Applications, Terminal, Stop, Checks, Logs, source updates, and the optional agent sandbox manager. Use arrows to move, Enter/Space to choose, and Esc/Q to go back. A terminal of at least 64 columns × 20 rows is required. Opening the menu starts no installers.

First setup asks for your project folder, a VNC password, and an SSH public key (or a separate SSH password). Review everything on one configuration screen and choose Save. Then choose Start / apply to build and launch. Sign in to applications interactively afterward.

The generated configuration enables browser desktop and SSH on **localhost only**. NVIDIA/CUDA, native VNC/Remmina, desktop audio, development ports, shared host settings and agent isolation are explicit choices. Changing features never deletes persistent volumes. Applications and files remain when services are stopped or disabled.

## One private profile, no personal settings in Git

Your settings are stored in `.deskharbor/config.json`, credentials in `.deskharbor/secrets/` and `.deskharbor/authorized_keys`. The generated Compose file is `.deskharbor/compose.json` (JSON is valid Compose YAML). These are local files excluded by both `.gitignore` and `.dockerignore`. They are never embedded in the image. Private files use mode 0600; created private directories use mode 0700.

Back up the ignored profile/secrets separately and back up your persistent Docker volumes. Git is not a backup of your private installation. Do not force-add private files to Git or publish an archive of the entire working directory.

The workstation has separate named volumes for home, SSH host keys and Homebrew. Project folders are bind-mounted under `/home/<workstation-user>/projects`. Extra host settings mounts are off by default: enabling `.codex`, `.gemini` or Antigravity settings explicitly shares their credentials/configuration read-write with the workstation.

## Features and connections

| Choice | What it enables | Default host port |
| --- | --- | --- |
| Browser desktop | GNOME Flashback, TigerVNC and noVNC | 6080 |
| Native VNC / Remmina | The same desktop through a published VNC port | 5901 |
| SSH | CLI tools, terminal and optional port forwarding | 20222 |
| Audio | Virtual desktop output and authenticated listening page | 6081 |
| NVIDIA / CUDA | CUDA development base and GPU access | — |

Start in local-only mode and use Status for connection addresses. To connect thin clients, choose Configuration → Network → LAN / VPN. Only enabled services and explicitly configured development ranges are published. DeskHarbor does not configure a router or VPN. HTTP/noVNC, audio HTTP and raw VNC are intended for a trusted LAN/VPN or SSH tunnel; they do not provide transport encryption. SSH public keys are recommended. VNC has an eight-significant-character password limit; the UI requires 6–8 ASCII characters, independently of SSH credentials.

For a browser tunnel from a client:

```bash
ssh -p 20222 -L 6080:127.0.0.1:6080 -L 6081:127.0.0.1:6081 <user>@<docker-host>
```

Then open `http://127.0.0.1:6080/` in the **client's browser**. If audio is enabled, open `http://127.0.0.1:6081/` on the client, sign in with the workstation username/VNC password and press Start audio. Keep that page open when using Remmina. Live PCM uses about 1.5 Mbit/s; MP3 uses less bandwidth but more buffering. Audio and VNC video are separate streams and are not synchronized. No host audio socket, sound device or microphone is shared.

One browser/Remmina client controls one shared desktop. Automatic resolution follows the current client's viewport; browser local scaling preserves the existing remote resolution. Run `display-mode auto` or `display-mode fixed 1920 1080` inside the workstation. Remmina-specific helper scripts remain available in `scripts/` for hosts that need the documented resize workaround; they change only the client launcher. noVNC uses its upstream clipboard panel; there is no custom automatic clipboard synchronization.

## Applications and persistence

Chrome, Tilix with dark theme, Git, Vim, GitHub CLI and basic development utilities are included. Choose Applications from the host menu, or run:

```bash
./deskharbor apps
```

The container-user menu installs/updates Sublime Text, Homebrew, nvm/Node/pyenv, Codex desktop, Codex CLI, Antigravity desktop and Antigravity CLI. Installation and updating are distinct operations. Antigravity desktop needs a supplied archive/HTTPS source; app sign-in remains interactive. Packages are downloaded from their publishers; no accounts or credentials are included.

The persistent home retains user tools, configurations and login state. Normal apt additions are recorded in the home and restored after recreation; this reinstalls packages rather than persisting the entire OS filesystem. Homebrew uses its own volume. Custom repositories or binaries placed outside persistent locations should be added to the image. Authentication may still need renewal after recreation.

The workstation user has passwordless sudo **inside the container**. Chrome and the desktop app launcher use `--no-sandbox` for compatibility with this container setup. The workstation is a trusted personal environment, not an isolation boundary for hostile commands.

## Commands and updates

```bash
./deskharbor setup        # interactive first setup
./deskharbor configure    # settings, features, credentials, mounts and ports
./deskharbor plan         # review local settings; does not start Docker
./deskharbor doctor       # host/Docker/Compose, credentials and mount checks
./deskharbor up           # build if needed; start/recreate using the saved profile
./deskharbor stop         # stop; retain all data
./deskharbor status
./deskharbor logs
./deskharbor shell
./deskharbor apps
./deskharbor update       # fast-forward source only; requires a clean source tree
./deskharbor sandbox      # optional host sandbox manager
```

Source updates do not restart the desktop; apply them when ready with Start / apply or `./deskharbor up`. Save open work before applying configuration/image changes: Docker may recreate the container. Credential edits are saved only when you save the configuration. Retry/back preserves your selected configuration after a failed operation. No menu operation runs `down -v`, prunes Docker, or automatically uninstalls applications.

## Optional agent sandbox

The advanced sandbox manager launches project-scoped disposable sibling containers via a restricted host SSH helper. It is disabled/not installed in the base setup. It has separate per-project homes, filtered source mounts, public-only proxy access and optional GPU permissions. It requires additional host FUSE/OpenSSH setup and sudo; it is not nested Docker and does not expose the Docker socket to the workstation. See [sandbox documentation](sandbox/README.md).

This custom sandbox is experimental and shares the host kernel. Project contents/history and supplied authentication remain readable to the agent; filename exclusions do not erase secrets from source history. Do not treat it as a VM or a complete security guarantee. Real-account agent login/model sessions need validation for the installed agent versions and restricted network. Keep agent versions current through deliberate rebuilds/updates.

## Adopt an existing installation

See [migration guide](docs/migration.md). Importing configuration never starts/restarts Docker. Adoption requires the existing named volumes and refuses empty replacements. Do not run two definitions concurrently against the same home.

## Validation and license

Run `python3 -m unittest discover -s tests -p 'test_*.py'` for host configuration/TUI planning tests. See [testing](docs/testing.md) for container, CUDA, audio and sandbox checks and their prerequisites. Host Docker runtime checks must be run on a real Docker host.

MIT license for this project's code. Third-party applications and dependencies retain their own licenses and terms.
