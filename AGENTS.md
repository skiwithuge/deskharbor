# Working on DeskHarbor

DeskHarbor provides a persistent Linux desktop in Docker, managed through a host CLI/TUI. It supports browser VNC, native VNC, SSH, optional audio and optional NVIDIA/CUDA. Keep first-time setup simple and advanced features opt-in.

## Configuration and persistence

- Keep public defaults generic. Store deployment-specific settings and credentials under the ignored `.deskharbor/` directory; exclude them from the Docker build context as well.
- Treat `.deskharbor/` as private input: inspect only what the task needs and never print credentials or include private files in commits, documentation, logs or fixtures.
- Preserve existing home, application and SSH-host-key volumes. Disabling a feature must retain its data. Adopted deployments require their existing volumes rather than silently creating empty replacements.
- Keep shared host settings optional. Preserve localhost binding for new deployments; LAN exposure must be an explicit configuration choice.
- Keep GPU access optional, with CPU mode working independently. CUDA workloads require a CUDA image and NVIDIA runtime support when GPU mode is enabled.

## Making changes

- Read `README.md` for the user-facing workflow. For sandbox changes, also read `sandbox/README.md` for the isolation model and known limitations.
- Keep host configuration and Compose generation in the Python CLI/TUI. Generated `.deskharbor/compose.json` is an output: change its source rather than editing it directly.
- Stage configuration and credential changes until the user saves. Cancellation should leave the previous deployment configuration intact.
- Explain interruptions before applying changes that rebuild or recreate a running workstation. Source edits alone do not authorize restarting the active desktop or changing host security settings.
- Keep optional applications installable and upgradable through the existing application menu/scripts. Preserve tools installed in persistent user storage across container recreation.
- Treat browser scaling, native VNC resolution and desktop UI zoom as separate controls. Test affected connection paths when changing display behavior.

## Verification

Read `docs/testing.md` and run the checks relevant to the modified behavior. Use temporary profiles, synthetic credentials and isolated test volumes; keep tests separate from the active workstation.

For host CLI/TUI changes, run:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

For image, service or sandbox changes, follow the corresponding runtime checks in the testing documentation. Report checks that could not run, especially when no Docker daemon or NVIDIA device is available. Unit tests alone do not establish that an image boots or that sandbox isolation works on a real host.
