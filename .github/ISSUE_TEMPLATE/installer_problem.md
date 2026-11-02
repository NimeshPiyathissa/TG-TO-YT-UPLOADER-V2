---
name: Installer problem
about: The installer stopped or behaved unexpectedly
labels: installer
---

**Which step failed?** (e.g. `[9/13] Web server and HTTPS`)

**The message it printed**

**Last 30 lines of `/var/log/tgyt-install.log`** (secrets are redacted by the installer; check anyway)
```
```

**Ubuntu version** (`lsb_release -a`), architecture (`uname -m`), RAM, provider:

**Domain mode:** own domain / sslip.io / loopback. Did `nslookup <your domain>` show the server IP?
