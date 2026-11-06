# DeskHarbor CLI sandbox

Launch Codex or `agy` from the workstation's VNC terminal. A constrained SSH key asks a host helper to start a disposable sibling container. Neither the workstation nor the workload receives the host Docker socket. This launcher does not restart the workstation.

## First setup: host terminal

Run from this repository on the physical host, as your normal Docker-enabled user:

```bash
./deskharbor sandbox
```

The manager opens a TUI menu (arrow keys / Enter, Space for checkboxes, Escape to go back):

- **First setup**: review settings, build if needed, install helper/client, register the project and check integration.
- **Add / edit project**: select an existing project or enter a new folder. Save registration without rebuilding or reinstalling the host helper.
- **Update image and helper**: rebuild from repository settings, refresh helper/client and run the integration check. Existing project registrations, GPU permissions, private tools and logins are preserved. Running sessions keep their current image.
- **Status / check**: show the current installation and registered projects; optionally run a disposable integration check.

Each operation shows editable settings together before starting. Detection fills the workstation and host address; mapping finds the corresponding project path inside the workstation. The **Install**, **Save**, or **Update** menu item starts the operation. A failed step offers **Retry**, **Edit settings**, or **Return to menu**, keeping the current inputs. Command output remains visible in terminal scrollback.

GPU permission is a checkbox. New projects default to CPU-only; `--gpu` preselects the checkbox for a new project. Editing an existing project loads its saved permission and exclusions. GPU-enabled registration still requires `deskharbor-sandbox --gpu codex` at launch.

```bash
./sandbox/setup-wizard.sh /home/deskharbor/projects/myproject --gpu
```

Optional initial values: `--host ADDRESS`, `--container NAME`, `--project-id ID`, repeatable `--hide RELATIVE_PATH`. `--rebuild` rebuilds during first setup; the Update action always rebuilds. CLI versions remain those specified by the repository build settings; rebuilding does not automatically change pinned versions.

The optional sandbox TUI requires `whiptail`. On Ubuntu: `sudo apt-get install whiptail`. Use a terminal at least 60 columns by 20 rows. Run as the normal host user, outside Docker; privileged steps request sudo. Host SSH port 22 must be reachable from the workstation, which must be running. The project must be bind-mounted into it. Setup places a new restricted launcher key in the workstation home, never your existing SSH keys or agent credentials.

Manual equivalent:

```bash
./sandbox/build.sh
sudo ./sandbox/setup-host.sh 192.0.2.10 deskharbor-workstation-1
sudo deskharbor-sandbox-admin register myproject /absolute/host/project \
  --workstation-path /absolute/workstation/project \
  --hide config/private.json
```

The host path and workstation path may differ. Register the same live source directory as seen on each side. Do not register your home, workspace parent, another project's parent, or an external Git worktree. Registration is host administration; agents cannot add folders or enable GPU. Add `--allow-gpu` at registration to permit opt-in GPU use.

The unified manager passes the selected workstation image and UID/GID to the sandbox builder. Standalone builds use your host UID/GID by default; override `WORKSTATION_IMAGE`, `WORKSTATION_UID` and `WORKSTATION_GID` when needed. Host/workstation ownership must match. Host installation currently targets Ubuntu with FUSE3, Python 3 and OpenSSH. It requires host sudo and Docker access.

## Daily use: VNC terminal

```bash
deskharbor-sandbox --list
cd /absolute/workstation/project
deskharbor-sandbox codex
deskharbor-sandbox agy
deskharbor-sandbox shell
deskharbor-sandbox --gpu codex
```

Run from the exact registered project root. Only one agent session per project runs at a time. Exiting removes the workload; the project and its private tool/login home remain. Ordinary Git commits and branches write to the real project.

Vim (`vim`) and GitHub CLI (`gh`) are inherited from the workstation image. Rebuild the workstation image first (`./workstation.sh build`), then choose **Update image and helper** in the host TUI to include them in new sandbox sessions. Run `gh auth login` inside `deskharbor-sandbox shell` for each project that needs GitHub access; its configuration persists in that project's private home.

Log in separately inside each project's sandbox. For Codex, launch `deskharbor-sandbox shell` then `codex login --device-auth`. `agy` may use a browser callback: keep the sandbox open and, in a second VNC terminal at the same project root, run `deskharbor-sandbox --forward PORT` for the callback port it reports. Open its login link in your workstation browser. CLI authentication through the restricted proxy has not yet been verified against a real account.

For a development server:

```bash
deskharbor-sandbox --publish 3000 shell
# inside the sandbox:
python3 -m http.server 3000 --bind 127.0.0.1
# open http://localhost:3000 in the workstation browser
```

Forwarding binds workstation loopback only. These commands bridge a guest service through the restricted helper; they cannot select a host or LAN destination. Port values must be 1024–65535. Remote clients need the workstation's existing approved forwarding mechanism to reach its loopback.

Install user tools under `/home/sandbox` (pip venvs, npm prefix, nvm/pyenv, local binaries). The OS is read-only and sudo is unavailable. The image inherits workstation development tools, Node and Python (plus CUDA when built from a CUDA workstation image), and installs both agent CLIs. Package managers must respect the proxy. Hardlinks are unavailable in the project view; use copies (`UV_LINK_MODE=copy` is set). Persistent tools and login data are visible to that project's future agents.

```bash
deskharbor-sandbox --reset  # prompts RESET; deletes only this project's sandbox home
```

Back up source independently: agents can edit/delete all allowed project files and rewrite its Git history. Home reset is not a project rollback.

## Boundary and limitations

- Live FUSE view hides `.env`, `.env.*`, `.ssh`, `.aws`, `.azure`, `.gnupg`, `secrets`, `*.pem`, `*.key` at every depth, including files created later. `--hide` adds designated relative paths. Even `.env.example` is hidden; use a differently named sanitized template.
- External symlinks, hardlinks, host sockets, FIFOs and devices are refused. No host home, desktop session, SSH agent, credentials, Docker socket or control configuration is mounted.
- Container has no network interface beyond its loopback. A host-controlled proxy allows public HTTP and HTTPS/CONNECT after DNS address validation; private/special addresses and current host interface addresses are blocked. DNS resolution happens on the host. Proxy-incompatible tools fail; there is no unrestricted fallback.
- Public internet still permits uploading readable project files and sandbox login tokens. Secret filenames are not content scanning: source, Git history, arbitrary filenames, and credentials you deliberately add remain readable. Public relays cannot be distinguished from other public endpoints.
- Non-root, all capabilities dropped, no-new-privileges, Docker default seccomp, read-only OS, resource limits. CPU is default; GPU exposes the NVIDIA driver and increases the attack surface.
- This is a custom local helper, not a hardened VM boundary or security audit. Workload and host share a kernel. It reduces routine agent access but cannot guarantee protection against kernel/driver exploits. It does not secure agents run outside this launcher or remove any pre-existing workstation privileges.
- Successful CLI `--version` and public HTTPS checks do not establish full Codex/agy model-session compatibility. Device/browser login and package installation need a real-account smoke test after host setup.

## Updates and checks

```bash
./sandbox/build.sh
sudo deskharbor-sandbox-admin image deskharbor-agent-sandbox:local
# helper/client changes:
sudo ./sandbox/setup-host.sh 192.0.2.10 deskharbor-workstation-1
```

The host pins an image ID. Changing a tag alone does not change active policy. Existing sessions retain their image; new sessions use the new pin. No workstation rebuild is required. Changing project registration requires host sudo.

Validation, from the host:

```bash
python3 -m venv /tmp/deskharbor-check-venv
/tmp/deskharbor-check-venv/bin/pip install -r sandbox/requirements.txt
cd sandbox
/tmp/deskharbor-check-venv/bin/python -m unittest discover -s tests -v
/tmp/deskharbor-check-venv/bin/python tests/kernel_probe.py
/tmp/deskharbor-check-venv/bin/python tests/container_probe.py --image deskharbor-agent-sandbox:local
# after host setup enables user_allow_other:
/tmp/deskharbor-check-venv/bin/python tests/end_to_end.py --image deskharbor-agent-sandbox:local
```

Checks use temporary source and home fixtures, never existing credentials. `kernel_probe.py` without host activation expects Docker to reject binding a rootless FUSE mount without `allow_other`; `end_to_end.py` requires the activated setting and verifies the real broker/FUSE/container path. The container probe checks the runtime and proxy independently of FUSE.

To disable: unregister projects with `sudo deskharbor-sandbox-admin unregister ID`, remove the single `deskharbor-workstation-sandbox` forced-command entry from host `~/.ssh/authorized_keys`, and remove the workstation launcher/key/config. Private homes live in host `~/.local/state/deskharbor-sandbox/homes`; delete only after reviewing saved logins/tools. `/etc/deskharbor-sandbox` and `/opt/deskharbor-sandbox` contain installed policy/code. If no other application needs `user_allow_other`, restore the saved FUSE config deliberately.
