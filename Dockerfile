# syntax=docker/dockerfile:1
ARG BASE_IMAGE=ubuntu:24.04
FROM ${BASE_IMAGE}
ARG DEBIAN_FRONTEND=noninteractive
ARG USER_NAME=deskharbor
ARG USER_UID=1000
ARG USER_GID=1000
ARG EXTRA_APT_PACKAGES=
ARG NODE_VERSION=22.23.4
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg git vim gh sudo openssh-server supervisor tini \
    pulseaudio pulseaudio-utils ffmpeg \
    dbus-x11 gnome-session-flashback gnome-terminal nautilus \
    tigervnc-standalone-server tigervnc-tools x11-xserver-utils xauth \
    python3 python3-venv python3-pip python3-numpy python3-websockify \
    fonts-dejavu fonts-liberation xdg-utils libgl1-mesa-dri mesa-utils \
    libnss3 libasound2t64 libgbm1 libsecret-1-0 gnome-keyring \
    build-essential pkg-config ripgrep tmux unzip xz-utils locales pipx \
    libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev libffi-dev \
    liblzma-dev libncurses-dev libgdbm-dev libgdbm-compat-dev uuid-dev tk-dev libzstd-dev \
    && locale-gen en_US.UTF-8 && rm -rf /var/lib/apt/lists/*
RUN install -d /etc/apt/keyrings && \
    curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/keyrings/chrome.gpg && \
    echo 'deb [arch=amd64 signed-by=/etc/apt/keyrings/chrome.gpg] https://dl.google.com/linux/chrome/deb/ stable main' > /etc/apt/sources.list.d/chrome.list && \
    curl -fsSL https://download.sublimetext.com/sublimehq-pub.gpg -o /etc/apt/keyrings/sublimehq-pub.asc && \
    printf 'Types: deb\nURIs: https://download.sublimetext.com/\nSuites: apt/stable/\nSigned-By: /etc/apt/keyrings/sublimehq-pub.asc\n' > /etc/apt/sources.list.d/sublime-text.sources && \
    apt-get update && apt-get install -y --no-install-recommends google-chrome-stable ${EXTRA_APT_PACKAGES} && rm -rf /var/lib/apt/lists/*
RUN curl -fsSLO https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz && \
    curl -fsSLO https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt && \
    grep " node-v${NODE_VERSION}-linux-x64.tar.xz$" SHASUMS256.txt | sha256sum -c - && \
    tar -xJf node-v${NODE_VERSION}-linux-x64.tar.xz -C /usr/local --strip-components=1 && \
    rm node-v${NODE_VERSION}-linux-x64.tar.xz SHASUMS256.txt
RUN git clone --depth 1 --branch v1.5.0 https://github.com/novnc/noVNC.git /opt/novnc && rm -rf /opt/novnc/.git
# Ubuntu's base image may already have an unused UID 1000 account.
RUN if getent passwd "${USER_UID}" >/dev/null; then userdel "$(getent passwd "${USER_UID}" | cut -d: -f1)"; fi && \
    if ! getent group "${USER_GID}" >/dev/null; then groupadd -g "${USER_GID}" "${USER_NAME}"; fi && \
    useradd -m -u "${USER_UID}" -g "${USER_GID}" -s /bin/bash "${USER_NAME}" && \
    printf '%s ALL=(ALL) NOPASSWD:ALL\n' "${USER_NAME}" > /etc/sudoers.d/workstation && chmod 440 /etc/sudoers.d/workstation
RUN apt-get update && apt-get install -y --no-install-recommends \
    tilix dconf-cli fonts-firacode fonts-cantarell fonts-noto-core fonts-noto-color-emoji && \
    update-alternatives --set x-terminal-emulator /usr/bin/tilix.wrapper && \
    fc-cache -f && rm -rf /var/lib/apt/lists/*
ENV WORKSTATION_USER=${USER_NAME} HOME=/home/${USER_NAME} DISPLAY=:1 \
    LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 LIBGL_ALWAYS_SOFTWARE=1 \
    PULSE_SERVER=unix:/tmp/runtime-${USER_UID}/pulse/native PULSE_SINK=workstation \
    PULSE_CLIENTCONFIG=/etc/workstation/audio/client.conf \
    ENABLE_DBUS=true ENABLE_SSH=true ENABLE_VNC=true ENABLE_WEB=true \
    ENABLE_AUDIO=false ENABLE_PULSE=false SSH_AUTH_MODE=key \
    BASH_ENV=/etc/workstation/bash-env.sh \
    NVIDIA_VISIBLE_DEVICES=void NVIDIA_DRIVER_CAPABILITIES=compute,utility \
    PATH=/home/${USER_NAME}/.local/bin:/home/${USER_NAME}/.local/npm/bin:/usr/local/cuda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/home/linuxbrew/.linuxbrew/bin:/home/linuxbrew/.linuxbrew/sbin
COPY scripts/ /opt/workstation/
COPY config/ /etc/workstation/
RUN chmod +x /opt/workstation/*.sh && \
    install -d /usr/local/share/gnome-session/sessions && \
    sed 's/org.gnome.SettingsDaemon.Power;//' /usr/share/gnome-session/sessions/gnome-flashback-metacity.session > /usr/local/share/gnome-session/sessions/deskharbor-flashback.session && \
    for name in install-codex install-codex-cli install-codex-app install-antigravity install-antigravity-cli update-codex update-codex-cli update-codex-app update-antigravity update-antigravity-cli install-dev-tools install-brew install-sublime update-sublime remember-system-tools restore-system-tools display-mode configure-terminal codex-app workstation-apps; do ln -s /opt/workstation/${name}.sh /usr/local/bin/${name}; done && \
    ln -s /opt/workstation/codex-app.sh /usr/local/bin/chatgpt && \
    cp /etc/workstation/workstation-codex-app.desktop /usr/share/applications/workstation-codex-app.desktop && \
    printf '%s\n' "${USER_NAME}" > /etc/workstation/user-name && \
    apt-mark showmanual | LC_ALL=C sort -u > /etc/workstation/base-manual-packages && \
    cp /etc/workstation/90-workstation-persistence /etc/apt/apt.conf.d/90-workstation-persistence && \
    cp /etc/workstation/profile.sh /etc/profile.d/workstation.sh && \
    install -d /run/sshd /run/dbus && \
    cp /etc/workstation/sshd.conf /etc/ssh/sshd_config && \
    ln -s /opt/workstation/browser.sh /usr/local/bin/google-chrome-stable && \
    ln -s /opt/workstation/browser.sh /usr/local/bin/google-chrome && \
    install -d /usr/local/share/applications && \
    sed 's|Exec=/usr/bin/google-chrome-stable|Exec=/usr/local/bin/google-chrome-stable|' /usr/share/applications/google-chrome.desktop > /usr/local/share/applications/google-chrome.desktop
WORKDIR /home/${USER_NAME}
EXPOSE 22 5901 6080 6081
HEALTHCHECK --interval=30s --start-period=60s --timeout=10s CMD /opt/workstation/healthcheck.sh
ENTRYPOINT ["/usr/bin/tini", "--", "/opt/workstation/entrypoint.sh"]
