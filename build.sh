#!/bin/bash

rm -vrf dist/ | echo "$(wc -l) files deleted"
mkdir -p dist/

rm -vrf build/ | echo "$(wc -l) files deleted"
mkdir -p build/

pyinstaller ./musicbar.spec
mkdir -p dist/dmg
cp -r "dist/MusicBar.app" dist/dmg

create-dmg \
  --volname "MusicBar" \
  --window-size 500 300 \
  --window-pos 200 100 \
  --icon-size 100 \
  --icon "MusicBar.app" 100 120 \
  --app-drop-link 380 120 \
  "dist/MusicBar.dmg" \
  "dist/dmg/"
