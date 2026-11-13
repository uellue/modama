# A throwaway host for the tests of ssh-tunnel@.service (run.sh): the client runs systemd
# (the default command), the far end only `sshd -D -e`. Also the host of the embedding
# service's unit test (prototypes/search-stack/embedding-service/tests/unit.sh).
FROM debian:trixie-20261027
RUN apt-get update && apt-get install -y --no-install-recommends \
        systemd systemd-sysv openssh-client openssh-server curl python3 python3-venv iproute2 procps openssl \
    && rm -rf /var/lib/apt/lists/* \
    && systemctl mask ssh.service ssh.socket getty@.service console-getty.service \
    && mkdir -p /run/sshd
STOPSIGNAL SIGRTMIN+3
CMD ["/lib/systemd/systemd"]
