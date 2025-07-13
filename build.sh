#!/bin/bash

rm -vrf dist/ | echo "$(wc -l) files deleted"
mkdir -p dist/

rm -vrf build/ | echo "$(wc -l) files deleted"
mkdir -p build/

pyinstaller ./musicbar.spec

codesign --force -s - "dist/Music Bar.app"

create-dmg \
  --volname "Music Bar" \
  --window-size 500 300 \
  --window-pos 200 100 \
  --icon-size 100 \
  --icon "Music Bar.app" 100 120 \
  --app-drop-link 380 120 \
  "dist/Music Bar.dmg" \
  "dist/Music Bar.app"
