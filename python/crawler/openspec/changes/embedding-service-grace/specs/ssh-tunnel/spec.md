# Spec Delta

## Purpose

A reusable systemd template for the SSH tunnels modama runs between hosts (`ssh -N -L`), with the key's restrictions on the far end, based on the instance in `deploy/beatepi/` (@weber, 2026-11-13: "good point to put the template there"). Its first user is the tunnel from staging to the embedding service on grace.

## ADDED Requirements

### Requirement: One instance per tunnel, configured outside the unit
The template `ssh-tunnel@.service` SHALL run, for an instance `NAME`, `ssh -N` to the destination and with the forwards named in `/etc/ssh-tunnel/NAME.conf`, with the key and the known-hosts file in `/etc/ssh-tunnel/NAME/`, as the local account `ssh-tunnel`. A new tunnel SHALL need no change to the unit file.

#### Scenario: The grace tunnel as an instance
- **WHEN** `/etc/ssh-tunnel/embed.conf` names the destination `embedtunnel@<grace>` and the forwards `-L 172.17.0.1:17656:127.0.0.1:7656 -L 172.17.0.1:11434:127.0.0.1:11434`, and `systemctl enable --now ssh-tunnel@embed` is run
- **THEN** `systemctl status ssh-tunnel@embed` shows `ssh -N` with both forwards, running as `ssh-tunnel`, and `172.17.0.1:17656` answers the service's `GET /health`

### Requirement: The tunnel fails instead of asking or hanging
The tunnel SHALL NOT wait for input: an unknown or changed host key, or a key that is refused, SHALL end `ssh` with an error in the journal. A destination that does not answer SHALL end the attempt within 10 seconds. No user or system `ssh_config` SHALL apply.

#### Scenario: An unknown host key
- **WHEN** the instance's known-hosts file does not hold the destination's host key
- **THEN** `ssh` ends at once, and `journalctl -u ssh-tunnel@NAME` says that the host key verification failed

#### Scenario: The destination does not answer
- **WHEN** the destination's address drops every packet
- **THEN** `ssh` ends within 10 seconds with a connection timeout in the journal, and systemd tries again 30 seconds later

#### Scenario: A system ssh_config
- **WHEN** `/etc/ssh/ssh_config` sets another identity file or `StrictHostKeyChecking no`
- **THEN** the tunnel uses only its instance's key and still refuses an unknown host key

### Requirement: The tunnel ends when a forward cannot be set up
`ssh` SHALL end when one of its forwards cannot be set up, instead of running without it.

#### Scenario: The local port is taken
- **WHEN** another process listens on a forward's local address and port
- **THEN** `ssh` ends with an error naming the port, and systemd starts it again after 30 seconds

### Requirement: The tunnel comes back by itself
When `ssh` ends for any reason other than a stop, systemd SHALL start it again after 30 seconds, without a limit on the number of restarts. A connection that no longer answers SHALL be noticed by `ssh` within about 4 minutes (keep-alive every 60 seconds, 3 missed).

#### Scenario: The far end reboots
- **WHEN** the destination is unreachable for 10 minutes and then reachable again
- **THEN** the tunnel works again within 30 seconds of the destination's SSH server being up, without anyone acting

### Requirement: The key opens nothing but its forwards
On the destination, the key SHALL be only in the `authorized_keys` of a `nologin` account of its own, with `restrict,port-forwarding`, one `permitopen="HOST:PORT"` per destination and `command="/usr/sbin/nologin"`; a `Match User` block SHALL allow local TCP forwards to those destinations only, no Unix-socket forwards, no TTY, no X11. Anything else SHALL be refused.

#### Scenario: A shell
- **WHEN** someone connects with the key and asks for a shell or a command
- **THEN** no shell or command runs, and the answer is `This account is currently not available.`

#### Scenario: A shell after the account's shell was changed
- **WHEN** the account's shell is `/bin/bash` by mistake and someone runs `ssh … id -un` with the key
- **THEN** no command runs: the forced command answers instead

#### Scenario: Two permitted destinations
- **WHEN** the key line has two `permitopen` options and the tunnel forwards to both
- **THEN** both forwards answer

#### Scenario: Another destination
- **WHEN** someone connects with the key and asks to forward to another host or port than the permitted one, for example `-L 9000:127.0.0.1:22`
- **THEN** the connection to it is refused, and the destination's `sshd` log says so

#### Scenario: The permitted port by another name
- **WHEN** the client's `-L` names `localhost` where the key line says `127.0.0.1`
- **THEN** the connection through the forward is refused (`permitopen` compares literally)

#### Scenario: A remote forward
- **WHEN** someone connects with the key with `-N -R 127.0.0.1:9000:127.0.0.1:22`
- **THEN** `ssh` reports `remote port forwarding failed for listen port 9000`, and nothing listens on the destination's port 9000

#### Scenario: A forward to a Unix socket on the destination
- **WHEN** someone connects with the key with `-N -L 127.0.0.1:9001:/run/some.socket`
- **THEN** a connection through the forward is refused, and the destination's `sshd` log says so

#### Scenario: A Unix socket created on the destination
- **WHEN** someone connects with the key with `-N -R /tmp/x.socket:127.0.0.1:22`
- **THEN** `ssh` reports that the remote forward failed, and no socket appears on the destination

#### Scenario: A terminal
- **WHEN** someone connects with the key with `ssh -tt`
- **THEN** `ssh` reports `PTY allocation request failed`

#### Scenario: What applies on the destination's sshd
- **WHEN** `sudo sshd -T -C user=<account>` runs on the destination
- **THEN** it shows `allowtcpforwarding local`, `allowstreamlocalforwarding no`, `permittty no`, `x11forwarding no` and `permitopen` with exactly the permitted destinations

### Requirement: The tunnel's address cannot be taken while it is down
Required before production, not for the prototype (accepted for the demo, @weber, 349): each forward SHALL listen on a port below 1024, with the template's account given `CAP_NET_BIND_SERVICE`, so that no unprivileged user can listen on that address while the tunnel is down.

#### Scenario: The tunnel is stopped
- **WHEN** the instance is stopped and an unprivileged user tries to listen on a forward's address and port
- **THEN** it fails with "Permission denied", and the instance listens there again once started
