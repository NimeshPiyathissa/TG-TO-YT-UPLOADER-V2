# 3. Domain, subdomain and DNS

Google refuses to send you back to a bare IP address after sign-in, so the admin panel needs a **hostname with real HTTPS**.
This page takes you from "I have a VPS IP" to "`https://upload.example.com` opens my panel".

**Contents:** [Pick an option](#pick-an-option) · [DNS in 5 minutes](#dns-in-5-minutes-what-the-words-mean) · [Spaceship](#spaceship-step-by-step) ·
[Cloudflare](#cloudflare-step-by-step) · [Other registrars](#other-registrars) · [Check the record](#check-the-record) ·
[Several subdomains on one VPS](#several-subdomains-on-one-vps) · [HTTPS, nginx and certificates](#https-nginx-and-certificates) ·
[Google redirect URI](#the-google-redirect-uri) · [Free sslip.io name](#option-b-free-sslipio-hostname-no-purchase) · [No hostname](#option-c-advanced-no-hostname)

The examples use **placeholders**. Replace them with your own values everywhere:

| Placeholder | What it is | Where you find yours |
|---|---|---|
| `example.com` | the domain you bought | your registrar's domain list |
| `upload.example.com` | the subdomain the panel will live on | you choose the `upload` part |
| `203.0.113.10` | the VPS's public IPv4 address | your VPS provider's dashboard; the installer also prints it |

(`203.0.113.10` belongs to a range reserved for documentation, so it can never be anyone's real server.)

## Pick an option

| Option | Cost | Best for |
|---|---|---|
| **A. Your own domain or subdomain** (recommended) | about $10/year, or free if you already own a domain | anything long-term |
| **B. Free `sslip.io` name** | free | trying it out |
| **C. No hostname** (self-signed certificate) | free | when a hostname is impossible; channels are linked through an SSH tunnel |

A **subdomain** (`upload.example.com`) is free once you own `example.com`, and keeps your main website untouched. That is what this guide uses.

## DNS in 5 minutes: what the words mean

| Term | Meaning |
|---|---|
| **A record** | "This name lives at this **IPv4** address." `upload.example.com → 203.0.113.10`. This is the one you need. |
| **AAAA record** | The same for **IPv6**. Only add one if your VPS has IPv6 *and* you want it; a wrong or old AAAA record breaks HTTPS for visitors who prefer IPv6. |
| **CNAME record** | "This name is an alias of another name." Not needed here; an A record is simpler and is what the installer checks. |
| **Host / Name** | The part before your domain: `upload` for `upload.example.com`, `@` for `example.com` itself. |
| **TTL** | How many seconds resolvers may cache the answer. Use 300 (5 minutes) or *Auto* while setting up, so fixes show up quickly. |
| **Propagation** | The time until resolvers around the world see a new or changed record. Usually minutes; occasionally up to an hour. A *changed* record can take as long as the **old** TTL. |
| **DNS cache** | Your computer and browser remember answers too. If a check from your PC shows the old value, flush it (`ipconfig /flushdns` on Windows) or test from the VPS. |

## Spaceship step by step

[Spaceship](https://www.spaceship.com) is a popular registrar. Labels in its dashboard change from time to time; look
for the closest match.

1. Sign in at spaceship.com.
2. Open **Domain Manager** (the list of your domains).
3. Click the domain, e.g. `example.com`.
4. Open its DNS settings (**Advanced DNS** / **DNS records**). If the domain uses another provider's nameservers (for example Cloudflare), Spaceship
   shows that here; add the record at that provider instead.
5. **Add record** (or edit the existing one with the same host).
6. Type: **A**.
7. Host: **`upload`** (just the subdomain part, without the domain).
8. Value / Points to: the VPS IP, e.g. **`203.0.113.10`**.
9. TTL: the shortest offered (e.g. 5 minutes or *Auto*). The exact choices vary.
10. **Save**. Then [check the record](#check-the-record).

The finished record:

| Type | Host | Value | TTL |
|---|---|---|---|
| A | upload | 203.0.113.10 | 300 |

If there was already an `A` or `AAAA` record for `upload` pointing somewhere else (a parking page, an old server), delete it. Two different
answers for one name make certificate issuance fail.

## Cloudflare step by step

Use this if your domain's nameservers are at Cloudflare (the registrar's DNS page will say so).

1. Sign in at dash.cloudflare.com and select the domain.
2. **DNS → Records → Add record**.
3. Type **A**, Name **`upload`**, IPv4 address **your VPS IP**, TTL **Auto**.
4. **Proxy status: DNS only (grey cloud).** Click the orange cloud to turn it grey.
5. **Save**.

**Why DNS only:** with the orange cloud ("Proxied"), the name resolves to Cloudflare's addresses instead of your server. The installer compares the
record with the server's IP and will report a mismatch. Cloudflare's proxy also sits between your users and the live-progress stream, and its
SSL setting must then be *Full (strict)* to avoid redirect loops. You can switch to *Proxied* later if you know you want it, but DNS only is the
tested setup.

## Other registrars

Namecheap (**Advanced DNS**), Porkbun (**DNS**), GoDaddy (**DNS → Manage**), Squarespace Domains (**DNS settings**): the record is always the same:
type `A`, host `upload`, value = your VPS IP, TTL 300 or Auto. For the bare domain the host is `@`.

## Check the record

Run any of these from your own computer, and once from the VPS. The answer must be your VPS IP, and only that.

```powershell
# Windows PowerShell
Resolve-DnsName upload.example.com -Type A
Resolve-DnsName upload.example.com -Type A -Server 1.1.1.1    # ask Cloudflare's resolver directly, skipping your cache
nslookup upload.example.com
ipconfig /flushdns                                              # if you still see an old answer
```

```bash
# Linux / macOS / the VPS
dig +short A upload.example.com
dig +short A upload.example.com @8.8.8.8                        # ask Google's resolver directly
dig +short AAAA upload.example.com                              # should be empty unless you set IPv6 on purpose
nslookup upload.example.com
```

You don't have to wait by hand: during setup the installer queries `1.1.1.1`, `8.8.8.8` and the server's own resolver, shows the exact record to add
if the answer is wrong, and can re-check every few seconds for up to 10 minutes.

## Several subdomains on one VPS

You can point as many names as you like at the same server, each with its own A record:

| Type | Host | Value |
|---|---|---|
| A | `upload` | `203.0.113.10` |
| A | `admin` | `203.0.113.10` |
| A | `api` | `203.0.113.10` |

nginx then decides which application answers by looking at the name the browser asked for (`server_name` in each *server block*).

**What this project uses:** exactly **one** hostname, the one you give the installer (`PUBLIC_HOST`). The admin panel, the OAuth callback and the
live-progress stream all live under it. There is **no** separate admin or API service; extra names like `admin.example.com` or `api.example.com`
are only useful for *other* applications you host on the same VPS, each with its own nginx server block and certificate. Don't point them at this
app's configuration.

To host something else on another subdomain of the same VPS (ports 80 and 443 are shared through nginx):

```bash
sudo nano /etc/nginx/sites-available/other-app.conf    # a server block with: server_name api.example.com; proxy_pass http://127.0.0.1:9000;
sudo ln -s /etc/nginx/sites-available/other-app.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d api.example.com                 # certificate for that name only
```

Leave `/etc/nginx/sites-available/tgyt.conf` alone; the installer manages it and rewrites it when you re-run it.

## HTTPS, nginx and certificates

The installer does all of this for you in step 9; this section explains what it set up, so you can check it.

| Piece | What the installer configures |
|---|---|
| **Port 80** | Answers Let's Encrypt's domain check (`/.well-known/acme-challenge/`) and redirects everything else to HTTPS. |
| **Port 443** | nginx terminates HTTPS for your hostname and forwards requests to the app on `127.0.0.1:8001` (never exposed directly). The live-progress stream (`/events`) is passed through unbuffered. |
| **Certificate** | A free Let's Encrypt certificate from `certbot` (webroot), for exactly your hostname. HSTS is on. |
| **Renewal** | `certbot.timer` renews it automatically before expiry; nginx is reloaded after each renewal. |
| **Firewall** | ufw allows SSH, 80 and 443 (or your custom panel port). |

Check it:

```bash
sudo tgyt doctor                              # HTTPS, certificate expiry, a renewal dry run and reachability, with fixes
curl -I https://upload.example.com/login      # expect: HTTP/1.1 200 OK
sudo nginx -t                                 # config syntax
systemctl list-timers certbot.timer           # next automatic renewal
```

**If the certificate fails** (the installer then falls back to a self-signed certificate and tells you): the A record isn't pointing at this server
yet, an AAAA record points elsewhere, a Cloudflare record is proxied, or your VPS provider's own firewall blocks port 80. Fix that and run
`sudo ./install.sh` again (choose *Keep my settings*). More in [Troubleshooting → SSL](10-troubleshooting.md#ssl).

## The Google redirect URI

Google sends you back to the panel after you approve access. It only allows addresses you registered in advance, and they must match **exactly**:

```
https://upload.example.com/oauth/callback      ← https:// + your hostname + /oauth/callback
```

- No trailing slash, no port (unless you chose a panel port other than 443, then e.g. `https://upload.example.com:8443/oauth/callback`).
- The installer prints the exact URI at the end, and the panel shows it again under **Channels → Link a channel** (with a copy button).
- **If you change the hostname later:** add the new URI in Google Cloud Console (APIs & Services → Credentials → your Web client → Authorized
  redirect URIs), run `sudo tgyt config PUBLIC_HOST`, then re-run the installer so nginx and the certificate follow. See [5.4](05-google-cloud.md#54-create-the-oauth-client-web-application).

## Option B: free `sslip.io` hostname (no purchase)

`sslip.io` is a free public service that turns an IP into a hostname: `203-0-113-10.sslip.io` always resolves to `203.0.113.10`.
Choose option 2 in the installer and it uses this automatically, with a normal Let's Encrypt certificate.

Trade-offs: you depend on a third-party service staying up, the name looks unprofessional, and if you ever change the server's IP the address
(and your Google redirect URI) changes. Fine for testing; use a real domain for anything long-term.

## Option C (advanced): no hostname

The installer's option 3 serves a self-signed certificate directly and links channels through an SSH tunnel or the offline helper
`tools/link_channel.py`. Browsers will warn about the certificate. Use only if you can't have a hostname.
See [Linking channels → loopback mode](07-linking-channels.md#advanced-no-hostname-loopback-mode).
