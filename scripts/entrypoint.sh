#!/usr/bin/env bash
set -euo pipefail
[[ ${AUDIO_PORT:-6081} =~ ^[0-9]+$ ]] && (( 10#${AUDIO_PORT:-6081} >= 1 && 10#${AUDIO_PORT:-6081} <= 65535 )) || { echo "Invalid AUDIO_PORT" >&2; exit 1; }
for name in ENABLE_DBUS ENABLE_SSH ENABLE_VNC ENABLE_WEB ENABLE_PULSE ENABLE_AUDIO; do
    [[ ${!name:-} == true || ${!name:-} == false ]] || { echo "Invalid service switch: $name" >&2; exit 1; }
done
uid=$(id -u "$WORKSTATION_USER")
gid=$(id -g "$WORKSTATION_USER")
export XDG_RUNTIME_DIR="/tmp/runtime-$uid"
[[ ${DISPLAY_WIDTH:-1920} =~ ^[0-9]+$ && ${DISPLAY_HEIGHT:-1080} =~ ^[0-9]+$ ]] || { echo 'Invalid display dimensions' >&2; exit 1; }
[[ ${DISPLAY_MODE:-auto} == auto || ${DISPLAY_MODE:-auto} == fixed ]] || { echo 'DISPLAY_MODE must be auto or fixed' >&2; exit 1; }
install -d -m 700 -o "$uid" -g "$gid" "$XDG_RUNTIME_DIR" "$HOME/.vnc" "$HOME/.ssh"
# Only own the home root, never recursively change ownership of host mounts.
chown "$uid:$gid" "$HOME"
install -d -m 755 -o "$uid" -g "$gid" /home/linuxbrew/.linuxbrew
runuser -u "$WORKSTATION_USER" -- mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications" "$HOME/Desktop"
if [[ ! -f $HOME/.bashrc ]]; then cp /etc/skel/.bashrc "$HOME/.bashrc"; chown "$uid:$gid" "$HOME/.bashrc"; fi
if [[ ! -f $HOME/.profile ]]; then cp /etc/skel/.profile "$HOME/.profile"; chown "$uid:$gid" "$HOME/.profile"; fi
if ! grep -q /etc/profile.d/workstation.sh "$HOME/.bashrc"; then
    printf '\nsource /etc/profile.d/workstation.sh\n' >> "$HOME/.bashrc"
fi
if [[ ${RESTORE_SYSTEM_TOOLS:-true} == true ]]; then
    if ! /opt/workstation/restore-system-tools.sh; then
        echo 'Some saved system tools could not be restored. Run restore-system-tools to retry.' >&2
    fi
fi
if [[ $ENABLE_VNC == true ]]; then
    vnc_password=$(cat /run/secrets/vnc_password)
    [[ ${#vnc_password} -ge 6 && ${#vnc_password} -le 8 ]] || { echo 'VNC password must have 6–8 characters.' >&2; exit 1; }
    printf '%s' "$vnc_password" | tigervncpasswd -f > "$HOME/.vnc/passwd"
    chmod 600 "$HOME/.vnc/passwd"
    chown "$uid:$gid" "$HOME/.vnc/passwd"
    unset vnc_password
fi
if [[ $ENABLE_AUDIO == true ]]; then
    python3 /opt/workstation/audio-server.py --prepare-auth /run/secrets/vnc_password "$XDG_RUNTIME_DIR/audio-auth.json" "$WORKSTATION_USER"
    chown "$uid:$gid" "$XDG_RUNTIME_DIR/audio-auth.json"
fi
[[ ${SSH_AUTH_MODE:-key} == key || ${SSH_AUTH_MODE:-key} == password ]] || exit 1
if [[ $ENABLE_SSH == true && ${SSH_AUTH_MODE:-key} == password ]]; then
    ssh_password=$(cat /run/secrets/ssh_password)
    [[ -n $ssh_password && $ssh_password != *$'\n'* ]] || { echo 'SSH password must be one nonempty line.' >&2; exit 1; }
    printf '%s:%s\n' "$WORKSTATION_USER" "$ssh_password" | chpasswd
    unset ssh_password
fi
if [[ $ENABLE_SSH == true && ${SSH_AUTH_MODE:-key} == key ]]; then
    [[ -s /etc/workstation/authorized_keys ]] || { echo 'SSH public keys are missing.' >&2; exit 1; }
    touch "$HOME/.ssh/authorized_keys"
    while IFS= read -r line; do
        [[ -z $line ]] || grep -Fqx -- "$line" "$HOME/.ssh/authorized_keys" || printf '%s\n' "$line" >> "$HOME/.ssh/authorized_keys"
    done < /etc/workstation/authorized_keys
    chmod 600 "$HOME/.ssh/authorized_keys"
    chown "$uid:$gid" "$HOME/.ssh/authorized_keys"
fi
sed "s/^PasswordAuthentication .*/PasswordAuthentication $([[ ${SSH_AUTH_MODE:-key} == password ]] && echo yes || echo no)/" /etc/workstation/sshd.conf > /etc/ssh/sshd_config
install -d -m 700 /var/lib/workstation/ssh
install -d -m 755 /run/sshd /run/dbus
for type in ed25519 rsa; do
    key="/var/lib/workstation/ssh/ssh_host_${type}_key"
    [[ -f $key ]] || ssh-keygen -q -t "$type" -N '' -f "$key"
done
/usr/sbin/sshd -t
mode=${DISPLAY_MODE:-auto}
[[ ! -f $HOME/.vnc/display-mode ]] || mode=$(cat "$HOME/.vnc/display-mode")
# Landing page offers both resizing policies; fixed server mode rejects all client resize requests.
cat > /opt/novnc/index.html <<EOF
<!doctype html><html><head><meta charset="utf-8"><title>DeskHarbor</title>
<style>body{font:18px system-ui;max-width:700px;margin:10vh auto;padding:24px}a{display:block;margin:24px 0}</style></head>
<body><h1>DeskHarbor</h1><p>One desktop shared by browser VNC and native VNC.</p>
<a href="vnc.html?autoconnect=true&amp;resize=$([[ $mode == auto ]] && echo remote || echo scale)&amp;shared=true">Connect ($mode resolution)</a>
<a href="vnc.html?autoconnect=true&amp;resize=scale&amp;shared=true">Connect with local scaling (multiple clients)</a>
<a id="audio-link" href="#" target="_blank" rel="noopener">Open workstation audio</a>
<script>const audioURL = new URL(window.location.href); audioURL.port = "${AUDIO_PORT:-6081}"; audioURL.pathname = "/"; audioURL.search = ""; audioURL.hash = ""; document.getElementById("audio-link").href = audioURL.href; document.getElementById("audio-link").hidden = "${ENABLE_AUDIO}" !== "true";</script>
<p>Use display-mode fixed WIDTH HEIGHT to prevent clients changing the desktop resolution.</p></body></html>
EOF
exec supervisord -c /etc/workstation/supervisord.conf
