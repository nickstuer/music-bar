# Notes

## Images
- Icons SVGs: https://www.reshot.com/free-svg-icons
- Emojis: https://getemoji.com

## Code Attempts

### Album Art Script
'''bash
tell application "Music"
    tell current track
        if exists (every artwork) then
            tell artwork 1
                get properties
            end tell
        else
            tell me to display alert "No Cover Art found."
        end if
    end tell
end tell
'''
