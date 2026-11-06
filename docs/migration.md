# Adopt an existing workstation without losing its home

Keep the original checkout as a private backup. Prepare DeskHarbor in a separate directory. Do not copy the original `.git`: use a fresh history and a GitHub noreply commit identity for the public repository.

From the new checkout:

```bash
./deskharbor import-legacy /absolute/path/to/existing-workstation
./deskharbor plan
```

The importer reads the original `.env` as data, never as shell code. It copies password files directly into ignored `.deskharbor/secrets/`, preserves the original user/UID/GID, network binding, service/development ports, CUDA image, display settings and host settings mounts. It retains Sublime Text through the private extra-package selection because it was included in the original base image rather than the apt additions manifest. It records the original Compose project and exact default volume names as **external required volumes**, retaining home, installed apps, SSH host keys and Homebrew. The original layout's project path inside the home is retained alongside the generic `/home/<user>/projects` alias. Existing sandbox helpers are not replaced or uninstalled during import; the renamed experimental sandbox is a separate explicit setup.

This importer targets the original single-service workstation layout with `home`, `ssh_host_keys` and `brew` volumes and the optional `compose.settings.yaml`. Custom container names, explicit volume-name overrides, extra Compose overlays or interpolated custom `.env` values require reviewing/editing the private JSON profile. No import is performed over an existing DeskHarbor profile.

On the original Docker host, review Configuration, then run:

```bash
./deskharbor doctor
```

Check the recorded volume names against `docker volume ls` and the existing installation before applying. Missing adopted volumes stop startup rather than creating empty ones. Import itself performs no Docker operations. The original checkout is unchanged, and running processes continue until you explicitly apply the new definition.

When you are ready, save desktop work and run `./deskharbor up` from the new checkout. It reuses the original Compose project and may recreate the workstation with the DeskHarbor image. Afterward manage that installation from only the new checkout. Keep the original checkout for rollback; do not start both copies. Persistent user applications/settings remain in the home; GUI or browser authentication may require renewal.

Shared host settings remain private because the profile, generated Compose manifest, credentials and local overrides are ignored and excluded from Docker build context. Before publishing, inspect `git ls-files`, scan staged files/history for secrets, and ensure that no private configuration files are tracked. Back up private profiles and Docker volume data outside the public repository.
