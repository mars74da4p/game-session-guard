# Game Session Guard

Game Session Guard is a Linux desktop utility for managing background processes during game sessions. It detects games, applies selected system optimizations, and restores suspended apps when the session ends.

## Features

- A desktop settings window with editable game and background-app lists.
- Automatic discovery of installed Steam games across the user's Steam libraries, including additional libraries configured in `libraryfolders.vdf`.
- Game detection by Steam install directory, plus exact process-name matching for non-Steam games and emulators.
- Optional background-app suspension, process priority boost, and kernel-cache clearing.
- Recovery of suspended processes when the game ends or the monitor is stopped with Ctrl+C.
- Per-user preferences and adjustable polling interval.

Steam games are detected from the local installed-game manifests. This covers the user's installed library without maintaining a stale copy of the entire Steam catalog. Double-click a game in the dashboard to add its title as a custom process name when needed.

## Requirements

- Linux, Python 3, and `psutil` (installed in a private virtual environment by the installer).
- Tkinter for the desktop window. On Debian/Ubuntu, install it with `sudo apt install python3-tk python3-venv` before running the installer.

## Install

```bash
git clone https://github.com/mars74da4p/game-session-guard.git
cd game-session-guard
sudo ./install.sh
```

The installer places the application in `/opt/game-session-guard`, the command in `/usr/local/bin/gameguard`, and the system defaults in `/etc/game-session-guard/config.json`. Existing system configuration is preserved.

## Run

```bash
gameguard --gui       # Open settings and control the monitor
gameguard --start     # Monitor from the terminal
gameguard --help      # Show command options
```

Run it as the desktop user for normal monitoring. Suspending processes is disruptive, so review the background-app list before enabling it. Raising priority or clearing kernel cache may require elevated privileges; cache clearing is off by default. When launched with `sudo`, the monitor scopes process actions to the user who invoked sudo.

## Configuration

The dashboard saves preferences to `~/.config/game-session-guard/config.json`. Set `GAMEGUARD_CONFIG` to use a different JSON file. `config.json` in the repository contains the initial game and background-app lists. Steam games installed after launch are picked up on the next monitor start or library refresh.
