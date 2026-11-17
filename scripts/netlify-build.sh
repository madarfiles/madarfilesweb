#!/bin/sh
# Netlify charges credits for every successful production deploy, so only one site builds:
# the live site (madarfiles). The test site (madarfiles-v2) builds only when the newest
# commit message contains [test]; otherwise its build stops here (failed builds are free)
# and its previous deploy stays online.
if [ "$SITE_NAME" = "madarfiles-v2" ] && ! git log -1 --pretty=%B | grep -q '\[test\]'; then
  echo "madarfiles-v2: skipped to save credits (add [test] to the commit message to build it)"; exit 1
fi
exec npm run build:netlify
