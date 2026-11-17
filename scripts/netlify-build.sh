#!/bin/sh
# Netlify charges credits for every successful production deploy, so only the live site
# builds on push. The test site carries MADAR_SITE_ROLE=test (a Netlify env var, set per
# site) and builds only when the newest commit message contains [test]; otherwise the
# build stops here (failed builds are free) and its previous deploy stays online.
if [ "$MADAR_SITE_ROLE" = "test" ] || [ "$SITE_ID" = "ecab0838-525a-40f2-ab9c-e3c2f0cbe50e" ]; then
  if ! git log -1 --pretty=%B | grep -q '\[test\]'; then
    echo "Test site skipped to save credits (add [test] to the commit message to build it)"; exit 1
  fi
fi
exec npm run build:netlify
