# Ansible control node for github.com/nph4/ansible. Replaces peco602/ansible-linux-docker, which was stuck on
# Python 3.8 and so on ansible-core 2.13 (too old for deb822_repository and for Ubuntu 26.04 hosts).
FROM python:3.14.7-slim-trixie

# ssh for managed hosts, git to pull the playbook repo cloned into /ansible
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-client git \
    && rm -rf /var/lib/apt/lists/*

# The full `ansible` package, not bare ansible-core: the playbooks need ansible.posix and community.docker
RUN pip install --no-cache-dir ansible==14.4.0

WORKDIR /ansible
