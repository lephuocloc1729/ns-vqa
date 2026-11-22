#!/bin/sh
# Writes /etc/nginx/auth.conf: a shared password when BASIC_AUTH_USER and BASIC_AUTH_PASSWORD are set,
# else nothing (open site). The password is hashed here; it is never stored in the image.
set -e
if [ -n "$BASIC_AUTH_USER" ] && [ -n "$BASIC_AUTH_PASSWORD" ]; then
  printf '%s:%s\n' "$BASIC_AUTH_USER" "$(printf '%s' "$BASIC_AUTH_PASSWORD" | openssl passwd -apr1 -stdin)" > /etc/nginx/.htpasswd
  printf 'auth_basic "Mat Luat";\nauth_basic_user_file /etc/nginx/.htpasswd;\n' > /etc/nginx/auth.conf
  echo "basic auth: on for user $BASIC_AUTH_USER"
else
  : > /etc/nginx/auth.conf
  echo "basic auth: off"
fi
