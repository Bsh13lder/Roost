#!/bin/sh
# Container entry (after tini). A stopped container starts again with its old files in place, so clear the
# X lock, the X and screen sockets and the browser's (Brave's) Singleton files first; then the supervisor takes over.
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1 /run/screen/vnc.sock /run/screen/cdp.sock \
      /home/comp/profile/SingletonLock /home/comp/profile/SingletonSocket /home/comp/profile/SingletonCookie
export DISPLAY=:1 HOME=/home/comp TZ=Europe/Madrid
# The desktop's shortcuts and settings (the home folder starts empty; the profile volume is left alone).
cp -R /usr/share/roost/home/. "$HOME"/ 2>/dev/null || true
exec roost-computerd
