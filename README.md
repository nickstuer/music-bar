# Music Bar

<img alt="GitHub Issues or Pull Requests" src="https://img.shields.io/github/issues/nickstuer/music-bar">

[![license](https://img.shields.io/github/license/nickstuer/music-bar.svg)](LICENSE)

Apple Music Bar for Mac OS X 10.6+. It also automatically updates your Discord 'Listening To' status so your friends can know what you're listening to with Apple Music. 

## 📖 Features

### Basic Music Controls
Quick access to Play/Pause/Next/Previous/Restart

### Discord Status
Updates your discord status to display the current song you're listening to.

### Application Volume Control
Volume control widget is tied directly to the application Music's volume and not the master volume.

### Playlists
Loads playlists automatically from Apple Music after the application is launched.

### Song Search
Easily search for and play a song directly from the status bar widget.


## 💎 Screenshots
<img src="https://github.com/nickstuer/music-bar/blob/main/docs/app_screenshot.png" width=50% height=50%>
<img src="https://github.com/nickstuer/music-bar/blob/main/docs/discord_screenshot.png" width=25% height=25%>

## 🛠 Install
MacOS only for now.

Download: https://github.com/nickstuer/music-bar/releases/download/v0.0.1/MusicBar.app.zip

## 💻 Development

#### Virtual Environment Setup
Helpful notes on how to set up a virtual enviroment for developing python applications using VS Code on MacOS.

<details><summary><b>Show Instructions</b></summary>

1. Open "Folder" in VS Code

2. Create Virtual Environment
    1. Press CMD + SHIFT + P and Select 'Python: Create Virtual Environment'
    2. Follow the prompts

3. Change Default Terminal in VS Code
    1. Press CMD + SHIFT + P and Select 'Terminal: Select Default Profile'
    2. Choose 'Command Prompt'

4. Test the Virtual Environment
    1. Press CTRL + SHIFT + ~ to open a terminal.
    2. Ensure the prompt begins with '(.venv)'

5. Install the pip dependenies
    1. Type: pip install -r requirements.txt
        
</details>

#### 📌 Dependencies
- Python 3.10 or greater
- rumps
- pypresence: https://github.com/qwertyquerty/pypresence/archive/master.zip (not the 'stable' build on PyPi, it's outdated)
- osascript
- darkdetect

## 🏆 Contributing
PRs accepted.

#### Bug Reports and Feature Requests
Please use the [issue tracker](https://github.com/nickstuer/music-bar/issues) to report any bugs or request new features.

#### Contributors

<a href = "https://github.com/nickstuer/music-bar/graphs/contributors">
  <img src = "https://contrib.rocks/image?repo=nickstuer/music-bar"/>
</a>

## 📃 License

[MIT © Nick Stuer](LICENSE)
