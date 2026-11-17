#!/bin/sh
# Netlify "ignore" command: exit 0 skips the build, exit 1 builds.
# - Test site (madarfiles-v2): builds every push to main.
# - Live site (madarfiles): builds only when the newest commit message contains [release].
# - Deploy previews are skipped on both to save build credits.
if [ "$CONTEXT" != "production" ]; then echo "Skipping $CONTEXT build"; exit 0; fi
if [ "$SITE_NAME" = "madarfiles" ]; then
  if git log -1 --pretty=%B | grep -q '\[release\]'; then echo "Release commit: building live site"; exit 1; fi
  echo "Live site waits for a [release] commit"; exit 0
fi
exit 1
