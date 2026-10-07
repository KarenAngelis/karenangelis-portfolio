"""Integrate this portfolio with the inspected VPS Caddy; preserve other routes."""
import datetime
import pathlib
import shutil
import subprocess

config = pathlib.Path("/opt/karsuel/infra/vps/Caddyfile.clycka")
snippet = pathlib.Path("/opt/karenangelis-portfolio/infra/Caddyfile.host-snippet").read_text()
original = config.read_text()
if "karenangelis.com" in original:
    raise SystemExit("A regra do domínio já existe. Revise antes de modificar.")
backup = config.with_name(config.name + ".before-karen-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
shutil.copy2(config, backup)
# Write in place: the existing container mounts this specific inode read-only.
config.write_text(original.rstrip() + "\n\n" + snippet)
try:
    subprocess.run(["docker", "exec", "karsuel-proxy-1", "caddy", "validate", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"], check=True)
    subprocess.run(["docker", "exec", "karsuel-proxy-1", "caddy", "reload", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"], check=True)
except subprocess.CalledProcessError:
    config.write_text(original)
    subprocess.run(["docker", "exec", "karsuel-proxy-1", "caddy", "reload", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"], check=False)
    raise
print(f"PORTFOLIO_ROUTE_ACTIVE; backup={backup}")
