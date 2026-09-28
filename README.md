# Game Session Guard 

**Game Session Guard** (`gameguard`) is a lightweight Linux background utility written in Python that automatically optimizes system performance for gaming sessions.

When a game is launched, it freezes unnecessary background applications (browsers, messaging apps), clears PageCache, and boosts the process priority of your game to ensure maximum FPS and eliminate micro-stutters. Once the game closes, all background apps are instantly restored.

## Features

- **Automated & Heuristic Detection:** Detects games via built-in database and path heuristics (`/steamapps/`, `Lutris`, `PortProton`, `Vulkan`).
- **Zero-Loss Background Freezing:** Suspends heavy background applications (`psutil.suspend()`) without closing them or losing session data.
- **CPU Priority & RAM Cleanup:** Raises process priority (`nice -10`) and clears unneeded kernel cache (`drop_caches`).
- **Safe State Recovery:** Automatically restores frozen processes on game exit or `Ctrl+C`.

## Installation

```bash
git clone https://github.com/mars74da4p/game-session-guard.git
chmod +x install.sh gameguard.py
sudo ./install.sh
