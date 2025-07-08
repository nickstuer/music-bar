pyinstaller ./musicbar.spec
mkdir -p dist/dmg
cp -r "dist/Music Bar.app" dist/dmg

create-dmg \
  --volname "Music Bar" \
  --window-size 500 300 \
  --window-pos 200 100 \
  --icon-size 100 \
  --icon "Music Bar.app" 100 120 \
  --app-drop-link 380 120 \
  "dist/Music Bar.dmg" \
  "dist/dmg/"
