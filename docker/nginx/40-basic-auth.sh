#!/bin/sh
# Writes /etc/nginx/auth.conf for the public site and /etc/nginx/admin_auth.conf for the admin site.
# Passwords are hashed here; they are never stored in the image.
#
# Public site: a login when BASIC_AUTH_USER and BASIC_AUTH_PASSWORD are set, else an open site.
#   The logins are the API's password file (USERS, a volume shared with the API, which writes the
#   shared login and every enabled tester account into it; docs/plans/admin-page.md). nginx reads
#   it on each request, so new accounts work at once. Without that file: the shared login only.
#   The admin console can turn the login off for everyone (Accounts, "login required"): the API then
#   writes OPEN next to the password file, and nginx skips the login while that file exists (checked
#   on each request, no reload). $site_user is the login passed to the API as X-Remote-User: empty on
#   an open site, because nginx does not check an Authorization header it does not ask for.
# Admin site (port 81, admin.<domain>): ADMIN_USER (default admin) and ADMIN_PASSWORD; without a
#   password every admin request gets 404.
set -e
USERS=/run/signcite-auth/users.htpasswd
OPEN=/run/signcite-auth/site_open
if [ -n "$BASIC_AUTH_USER" ] && [ -n "$BASIC_AUTH_PASSWORD" ]; then
  printf '%s:%s\n' "$BASIC_AUTH_USER" "$(printf '%s' "$BASIC_AUTH_PASSWORD" | openssl passwd -apr1 -stdin)" > /etc/nginx/.htpasswd
  file=/etc/nginx/.htpasswd
  if grep -q "^$BASIC_AUTH_USER:" "$USERS" 2>/dev/null; then file=$USERS; fi
  cat > /etc/nginx/auth.conf <<EOF
set \$site_auth "SignCite";
set \$site_user \$remote_user;
if (-f $OPEN) { set \$site_auth off; set \$site_user ""; }
auth_basic \$site_auth;
auth_basic_user_file $file;
EOF
  echo "basic auth: on ($file)"
else
  printf 'set $site_user "";\n' > /etc/nginx/auth.conf
  echo "basic auth: off"
fi
if [ -n "$ADMIN_PASSWORD" ]; then
  printf '%s:%s\n' "${ADMIN_USER:-admin}" "$(printf '%s' "$ADMIN_PASSWORD" | openssl passwd -apr1 -stdin)" > /etc/nginx/.admin_htpasswd
  printf 'auth_basic "SignCite admin";\nauth_basic_user_file /etc/nginx/.admin_htpasswd;\n' > /etc/nginx/admin_auth.conf
  echo "admin site: on for ${ADMIN_USER:-admin}"
else
  printf 'return 404;\n' > /etc/nginx/admin_auth.conf
  echo "admin site: off (no ADMIN_PASSWORD)"
fi
