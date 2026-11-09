# Install DeskHarbor

This guide takes a new installation from a Linux host to a desktop in your browser. Start with CPU mode; NVIDIA/CUDA can be enabled after its host prerequisites are ready. These steps install software on your host only when you run the commands yourself.

## 1. Choose the computer that runs the workstation

Use a Linux x86-64 computer with administrator (`sudo`) access and an internet connection. Ubuntu 24.04 LTS is the walkthrough below; it is a documented starting point, not yet a certification from a clean-host test. Run the commands in that computer's terminal, outside any Docker container. An SSH session into that Linux computer also works.

Your laptop, Mac or phone can be the client: it only needs a browser or VNC client. The Linux host must remain on while you use the desktop. The first build downloads a desktop environment and applications; optional CUDA images add substantial downloads and disk use. Allow the build to finish before connecting.

Check the architecture:

```bash
uname -m
```

Continue if it prints `x86_64`. ARM hosts are not currently supported by DeskHarbor.

## 2. Prepare Ubuntu

Install the small host tools used to download and manage DeskHarbor:

```bash
sudo apt update
sudo apt install -y git python3 openssh-client ca-certificates curl
python3 -c 'import curses; print("Python and terminal UI support are ready")'
```

No Python virtual environment or pip packages are needed for the main menu. The optional sandbox has separate dependencies and can wait until the desktop works.

For other Linux distributions, install Git, Python 3 with curses, OpenSSH client tools and Docker Engine with its Compose plugin using the distribution-specific instructions. See [Docker's supported platforms](https://docs.docker.com/engine/install/). The Ubuntu commands below are not intended for Debian, Fedora or Ubuntu derivatives.

## 3. Install Docker, if needed

Already using Docker? Run these commands **without sudo**:

```bash
docker info
docker compose version
```

If both succeed, skip to step 4. If Docker is installed but reports a permission or connection error, see the table at the end before installing anything again.

For a new Ubuntu Docker installation, use the official package repository. If this computer already has another Docker/containerd installation, review the conflicts in [Docker's Ubuntu installation instructions](https://docs.docker.com/engine/install/ubuntu/) before replacing packages.

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
```

Allow your normal account to manage Docker. Membership of this group grants root-level control of the host, as explained in [Docker's post-installation guide](https://docs.docker.com/engine/install/linux-postinstall/).

```bash
sudo groupadd --force docker
sudo usermod -aG docker "$USER"
```

**Sign out of your desktop or SSH session completely, then sign back in.** Opening another terminal alone does not refresh group membership. Then check, without `sudo`:

```bash
docker run --rm hello-world
docker compose version
```

The first command should print Docker's hello-world success message. The second should print the installed Compose plugin version. Use `docker compose` (with a space); the older `docker-compose` command is not used by DeskHarbor. Run DeskHarbor as your normal account, not with `sudo`.

## 4. Download and open DeskHarbor

```bash
git clone https://github.com/skiwithuge/deskharbor.git
cd deskharbor
./deskharbor
```

While the repository is private, your GitHub account needs access; use your authenticated Git workflow if HTTPS cloning fails. Once public, the command works without a GitHub account.

A menu should open. Make the terminal at least 64 columns wide and 20 rows high. Navigate with arrows, choose with Enter/Space, and go back with Esc/Q. Opening the menu does not start the workstation.

## 5. Configure your first desktop

Choose **First setup / Configuration**:

1. Choose a host project folder. The default is suitable for a new installation; DeskHarbor creates it when starting. Files there are shared with the workstation.
2. Set a VNC password of 6–8 ASCII characters. This is the password used to open the desktop; it is separate from your Linux login.
3. Choose SSH authentication. Use an existing public key ending in `.pub`, or choose a separate SSH password of at least 12 characters. Supply only the public key, never a private key. Password authentication is available if you do not have a key yet.
4. Keep browser desktop and SSH enabled, local networking selected, and GPU off for the first CPU-mode test. Optional audio and native VNC can be enabled later.
5. Review the configuration and choose **Save**.

Keys are optional. If you want a dedicated key, run `ssh-keygen -t ed25519 -f ~/.ssh/deskharbor_ed25519` on the computer you will connect from, then provide the contents/file `deskharbor_ed25519.pub` during setup. Keep the file without `.pub` on that client.

Choose **Checks**. Resolve any reported problem before choosing **Start / apply**. DeskHarbor builds the image and starts the services. The first build takes longer than later starts; keep the terminal open until it finishes. Choose **Status** to see the connection addresses.

## 6. Open the desktop

On the Linux host itself, open [the local desktop page](http://127.0.0.1:6080/) and connect with the VNC password from setup. If you changed the browser port, use the address shown by Status. Chrome, Tilix and the base development tools should be available inside the desktop. Choose **Applications** in the host menu to install optional applications; sign in to them yourself afterward.

On a different device, `127.0.0.1` refers to that device, not your Linux host. Choose **Configuration → Network → LAN / VPN**, save and apply, then use the host's address shown by Status in place of `<docker-host-ip>`. Only use this access on a trusted LAN/VPN; browser/VNC traffic is not encrypted. See [Features and connections](../README.md#features-and-connections) for SSH tunnels and audio. DeskHarbor does not create a VPN or configure your router.

For later visits, leave the host running and reconnect to the same address. Use **Stop** when you want to stop the workstation while retaining its data. To change settings, reopen `./deskharbor`, save your choices and apply them. Save open desktop work first because applying changes can recreate the container. Keep backups of your projects, Docker volumes and ignored `.deskharbor/` profile.

## Optional: enable NVIDIA/CUDA

CPU mode provides the desktop without NVIDIA preparation. To run CUDA workloads:

1. Install an appropriate NVIDIA driver through your Linux distribution's driver tools. Check that `nvidia-smi` works on the host.
2. Follow [NVIDIA's Container Toolkit installation and Docker configuration guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html). Configuring the runtime changes Docker's host configuration; its daemon restart can interrupt existing containers, so schedule it accordingly.
3. Enable **NVIDIA / CUDA** in DeskHarbor Configuration, save, run Checks and apply. This selects a CUDA development image and requests GPU access. The image's CUDA version must be compatible with your host driver.

DeskHarbor checks for the host GPU and runtime; it does not install drivers or reconfigure Docker itself. CUDA compute access does not provide accelerated desktop rendering.

## If a step fails

| What you see | What to do |
| --- | --- |
| `docker: command not found` | Complete Docker installation in step 3. |
| Docker socket `permission denied` | Complete the Docker group step and sign out/in; verify `docker info` without sudo. |
| Cannot connect to the Docker daemon | On the Ubuntu setup above, check `sudo systemctl status docker`; start it with `sudo systemctl start docker` if stopped. |
| `compose` is not a Docker command | Install `docker-compose-plugin` from Docker's configured package repository. |
| Python cannot import `curses` | Install your distribution's Python curses package; on Ubuntu, check that the system `python3` is being used. |
| Repository not found / authentication failed | The repository may still be private. Use a GitHub account with access; no Docker change is needed. |
| Menu cannot fit / terminal error | Use an interactive terminal, enlarge it to at least 64×20 and launch again. |
| Port already allocated | Choose unused service ports in Configuration; leave existing services alone. |
| Browser cannot connect | Wait for Start / apply to finish, then check Status and Logs. On another device, use the host IP and configure LAN/VPN access. |
| NVIDIA checks fail | Keep CPU mode while preparing the host driver/toolkit, then enable GPU again. |

For a build/start failure, use **Logs** or `./deskharbor logs` from the repository directory. Include the failing step and relevant error when asking for help, with passwords and tokens removed. A successful prerequisites check is not a substitute for testing the running desktop.
