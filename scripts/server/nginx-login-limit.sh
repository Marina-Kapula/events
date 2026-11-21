#!/usr/bin/env bash
# Limits login attempts in Dokku's nginx. Runs on the server, after `dokku apps:create <APP>`.
# From your laptop:
#   ssh <SSH_USER>@<VPS_IP> 'bash -s -- <APP>' < scripts/server/nginx-login-limit.sh
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: ssh <SSH_USER>@<VPS_IP> 'bash -s -- <APP>' < scripts/server/nginx-login-limit.sh" >&2
  exit 2
fi
app=$1
name=${app//-/_} # nginx variable and zone names can't contain hyphens

# The zone. It goes in the http block, which includes /etc/nginx/conf.d/*.conf. Requests whose
# key is empty (everything but a login POST) aren't counted.
sudo tee "/etc/nginx/conf.d/$app-login-limit.conf" >/dev/null <<CONF
map "\$request_method:\$uri" \$${name}_login_client {
    "~^POST:/(accounts|admin)/login/\$" \$binary_remote_addr;
    default "";
}
limit_req_zone \$${name}_login_client zone=${name}_login:1m rate=5r/m;
CONF

# The limit. Dokku includes the app's nginx.conf.d/*.conf in its server blocks (80 and 443).
sudo -u dokku mkdir -p "/home/dokku/$app/nginx.conf.d"
sudo -u dokku tee "/home/dokku/$app/nginx.conf.d/login-limit.conf" >/dev/null <<CONF
limit_req zone=${name}_login burst=5 nodelay;
limit_req_status 429;
CONF

# Django sends HSTS already; without this, responses carry two.
sudo dokku nginx:set "$app" hsts false

sudo nginx -t
sudo dokku proxy:build-config "$app"
