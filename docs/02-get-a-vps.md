# 2. Get a VPS and log in with SSH

A **VPS** is a computer you rent that runs 24/7. The uploader needs one because it must stay online to receive your videos.

## What to buy

| | Minimum | Recommended |
|---|---|---|
| OS | **Ubuntu 26.04 LTS** (tested); 24.04 / 22.04 LTS are accepted by the installer but not yet tested for v1.0.1 | Ubuntu 26.04 LTS |
| CPU | 1 vCPU | 2 vCPU |
| RAM | 1 GB (the installer adds a 2 GB swap file) | 2 GB or more |
| Disk | 20 GB | **40 GB+** — every video is stored on disk while it uploads; a 4 GB video needs ~5 GB, plus a 5 GB safety margin |
| Network | public IPv4 address, ports 22, 80, 443 reachable | — |
| Architecture | x86_64 or arm64 | — |

Any provider works (Hetzner, DigitalOcean, Vultr, Linode, AWS Lightsail, Azure, Oracle, a local provider...).
Prices are typically $4–12 per month for the recommended size. Pick a region close to you (it barely matters for uploads).

> **Avoid ephemeral storage.** Some clouds (for example Azure's `/mnt` disk) wipe temporary disks on resize or maintenance.
> The installer keeps all data on the normal system disk on purpose; don't move it to a "temporary" disk.

## When creating the server

1. Choose **Ubuntu 26.04 LTS** as the image (24.04 LTS also works with the installer, but hasn't been re-tested for v1.0.1).
2. Add your **SSH key** if the provider offers it (recommended; see below). Otherwise the provider emails/shows a root password.
3. Note the server's **public IP address** (for example `203.0.113.10`).
4. If the provider has its own **firewall / security group**, allow inbound **TCP 22, 80 and 443**. (Port 80 is needed for the free HTTPS certificate.)

## Logging in with SSH

**Windows 10/11, macOS, Linux:** open a terminal (Windows: *PowerShell* or *Windows Terminal*) and run:

```bash
ssh root@203.0.113.10          # use ubuntu@... or the user your provider names
```

The first time it asks `Are you sure you want to continue connecting?`: type `yes`. Then type the password (nothing appears while typing; that is normal),
or it logs you in straight away if you set up a key.

If you log in as a normal user (for example `ubuntu`) rather than root, put `sudo` in front of the install command.

### Creating an SSH key (recommended)

```bash
ssh-keygen -t ed25519 -C "my-vps"          # press Enter to accept the defaults; set a passphrase if you like
cat ~/.ssh/id_ed25519.pub                  # copy this single line into your provider's "SSH keys" box
```

On Windows PowerShell the same commands work; the file is `C:\Users\<you>\.ssh\id_ed25519.pub`.
Keep the *private* file (`id_ed25519`, no `.pub`) secret.

Once key login works, the installer can optionally switch off password logins ([docs/11-security.md](11-security.md)).

### Adding your key to a server that already exists

Linux/macOS: `ssh-copy-id root@203.0.113.10`. Windows PowerShell has no `ssh-copy-id`; this one line does the same:

```powershell
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub | ssh root@203.0.113.10 "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

Then `ssh root@203.0.113.10` should log in without asking for the server password.

## A separate admin user (recommended)

Working as `root` all the time makes mistakes expensive. Create your own user with `sudo` rights and use it from now on (as root, once):

```bash
adduser deploy                                   # pick a strong password; the other questions can stay empty
usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy   # lets your SSH key log in as deploy too
```

Open a **second** terminal and check `ssh deploy@203.0.113.10` and then `sudo -v` work **before** you close the root session.
From here on, run the installer and `tgyt` with `sudo`. (Many providers already create such a user, e.g. `ubuntu`; then just use that one.)

## Prepare the server

```bash
sudo apt update && sudo apt full-upgrade -y      # latest security updates
sudo reboot                                      # only if it says a restart is required; log in again afterwards
```

Quick health check before installing (the installer checks all of this again and explains anything wrong):

```bash
lsb_release -ds                    # Ubuntu 26.04.x LTS (or 24.04.x)
nproc; free -h; df -h /            # CPUs, RAM, free disk
curl -sI https://api.telegram.org | head -1     # internet access: expect an HTTP status line
```

**Don't set up the firewall yourself first.** The installer configures ufw (SSH, 80, 443) and fail2ban for you in step 10; turning ufw on by hand
without allowing SSH can lock you out. Leave the folders alone too: the installer creates `/opt/tgyt-uploader`, `/var/lib/tgyt` and `/etc/tgyt`
with the right owners and permissions.

**Next:** point a domain at the server ([3. Domain and DNS](03-domain-and-dns.md)).
