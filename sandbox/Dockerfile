# syntax=docker/dockerfile:1
ARG WORKSTATION_IMAGE=deskharbor:local
FROM ${WORKSTATION_IMAGE}
ARG CODEX_VERSION=0.167.0
ARG USER_UID=1000
ARG USER_GID=1000
USER root
RUN rm -f /etc/sudoers.d/workstation && \
    useradd -M -o -u ${USER_UID} -g ${USER_GID} -s /bin/bash sandbox && \
    install -d -o ${USER_UID} -g ${USER_GID} /home/sandbox && \
    npm install --global @openai/codex@${CODEX_VERSION}
COPY deskharbor_sandbox /opt/deskharbor-sandbox/deskharbor_sandbox
COPY run-agent.py /opt/deskharbor-sandbox/run-agent.py
COPY install-agy.sh /opt/deskharbor-sandbox/install-agy.sh
RUN chmod 755 /opt/deskharbor-sandbox/*.py /opt/deskharbor-sandbox/*.sh
USER sandbox
ENV HOME=/home/sandbox BASH_ENV="" DISPLAY="" NVIDIA_VISIBLE_DEVICES=void
RUN /opt/deskharbor-sandbox/install-agy.sh
USER root
RUN install -m 755 /home/sandbox/.local/bin/agy /usr/local/bin/agy && \
    rm -rf /home/sandbox/.local
USER sandbox
ENV PYTHONPATH=/opt/deskharbor-sandbox
WORKDIR /project
ENTRYPOINT ["/usr/bin/python3", "/opt/deskharbor-sandbox/run-agent.py"]
HEALTHCHECK NONE
