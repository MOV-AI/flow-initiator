# === Flow-Initiator
ARG DOCKER_REGISTRY="registry.cloud.mov.ai"
ARG ENV="qa"
ARG BASE_IMAGE="spawner-base-noetic"
ARG TAG="v3.1.9"
FROM ${DOCKER_REGISTRY}/${ENV}/${BASE_IMAGE}:${TAG} AS Flow-Initiator

# Labels
LABEL description="MOV.AI Flow initiator"
LABEL maintainer="devops@mov.ai"
LABEL movai="flow-initiator"
LABEL environment="release"

### Environment config

ENV MOVAI_ENV=${ENV} \
    USER_NAME=movai

USER root

COPY docker/requirements.txt /tmp/requirements.txt

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
# hadolint ignore=DL3008
RUN \
    --mount=type=cache,target=/var/cache/apt \
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg  && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null  && \
    apt-get update > /dev/null && \
    apt-get install -y --no-install-recommends docker-ce-cli && \
    groupadd docker && \
    gpasswd -a $USER_NAME docker && \
    python3 -m pip install --upgrade --no-cache-dir -r /tmp/requirements.txt && \
    # Clean apt
    apt-get autoremove -y && \
    apt-get clean -y > /dev/null && \
    rm -rf /var/cache/apt/* && \
    rm -rf /var/lib/apt/lists/* && \
    # Clean temp files
    rm -rf /tmp/*

# Run everything as flow user
USER ${USER_NAME}