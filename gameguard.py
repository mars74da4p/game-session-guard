#!/usr/bin/env python3
"""
game-session-guard - Automatic FPS & System Resource Optimizer
License: MIT
"""

import os
import sys
import time
import json
import psutil
import argparse
from pathlib import Path

# Terminal colors
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
CYAN = '\033[0;36m'
NC = '\033[0m'

CONFIG_PATH = Path(__file__).parent / "config.json"

DEFAULT_CONFIG = {
    "target_games": [
        "steam", "steamwebhelper", "heroic", "lutris", "bottles", "portproton",
        "javaw", "java", "wine", "wine64", "proton", "gamescope",
        "minecraft", "csgo", "cs2", "dota2", "fortnite", "roblox",
        "vita3k", "rpcs3", "yuzu", "pcsx2", "ppsspp", "dolphin-emu", "retroarch"
    ],
    "apps_to_suspend": [
        "chrome", "chromium", "firefox", "zen", "brave", "opera", "vivaldi", "yandexbrowser", "edge",
        "telegram-desktop", "telegram", "discord", "vesktop", "webcord", "slack",
        "spotify", "vlc", "obs", "qbittorrent"
    ]
}

def load_config():
    if not CONFIG_PATH.exists():
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        return DEFAULT_CONFIG

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
            games = list(set(DEFAULT_CONFIG["target_games"] + user_cfg.get("target_games", [])))
            apps = list(set(DEFAULT_CONFIG["apps_to_suspend"] + user_cfg.get("apps_to_suspend", [])))
            return {"target_games": games, "apps_to_suspend": apps}
    except Exception:
        return DEFAULT_CONFIG

def is_heuristic_game(proc) -> bool:
    """Smart auto-detection based on process paths and command line arguments."""
    try:
        cmdline = " ".join(proc.cmdline()).lower()
        exe_path = proc.exe().lower() if proc.exe() else ""

        game_indicators = [
            "steamapps/common", ".steam", "heroic/games", "lutris/games", 
            "portproton", "gamescope", "vulkan", "opengl", ".var/app"
        ]

        for indicator in game_indicators:
            if indicator in cmdline or indicator in exe_path:
                if not any(x in cmdline for x in ["chrome", "firefox", "telegram", "systemd"]):
                    return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return False

def find_running_targets(target_names):
    running = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'exe']):
        try:
            p_name = proc.info['name'].lower()
            is_matched = any(target in p_name for target in target_names) or is_heuristic_game(proc)
            if is_matched:
                running.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return running

def get_apps_to_suspend(app_names):
    procs = []
    current_pid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if proc.info['pid'] == current_pid:
                continue
            p_name = proc.info['name'].lower()
            for app in app_names:
                if app.lower() in p_name:
                    procs.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return procs

def suspend_apps(apps):
    suspended_count = 0
    for proc in apps:
        try:
            proc.suspend()
            suspended_count += 1
        except Exception:
            pass
    return suspended_count

def resume_apps(apps):
    resumed_count = 0
    for proc in apps:
        try:
            proc.resume()
            resumed_count += 1
        except Exception:
            pass
    return resumed_count

def boost_game_priority(game_procs):
    for proc in game_procs:
        try:
            proc.nice(-10)
        except Exception:
            pass

def drop_system_cache():
    """Drop non-critical PageCache to free RAM before game launches."""
    try:
        if os.geteuid() == 0:
            with open("/proc/sys/vm/drop_caches", "w") as f:
                f.write("1\n")
    except Exception:
        pass

def monitor_session():
    config = load_config()
    target_games = config.get("target_games", [])
    apps_to_suspend = config.get("apps_to_suspend", [])

    print(f"{CYAN}[*] Game Session Guard started.{NC}")
    print(f"Monitoring {YELLOW}{len(target_games)}{NC} database targets + Heuristic Detection.")
    print(f"Suspend list contains {YELLOW}{len(apps_to_suspend)}{NC} heavy apps.")
    print(f"{GREEN}[+] Waiting for game launch...{NC}\n")

    is_gaming = False
    suspended_processes = []

    try:
        while True:
            running_games = find_running_targets(target_games)

            if running_games and not is_gaming:
                is_gaming = True
                game_names = ", ".join(set(p.name() for p in running_games))
                print(f"{GREEN}[!] Game detected: {game_names}{NC}")
                print(f"{CYAN}[*] Optimizing system for peak FPS...{NC}")

                # Free system RAM cache
                drop_system_cache()

                # Boost priority
                boost_game_priority(running_games)

                # Suspend background applications
                suspended_processes = get_apps_to_suspend(apps_to_suspend)
                count = suspend_apps(suspended_processes)
                print(f"{GREEN}[✓] Suspended {count} background processes.{NC}")
                print(f"{YELLOW}[*] Game session active. Enjoy your smooth gaming!{NC}\n")

            elif not running_games and is_gaming:
                is_gaming = False
                print(f"{YELLOW}[!] Game session ended.{NC}")
                print(f"{CYAN}[*] Restoring background processes...{NC}")

                count = resume_apps(suspended_processes)
                suspended_processes.clear()
                print(f"{GREEN}[✓] Resumed {count} background processes.{NC}")
                print(f"{GREEN}[+] Waiting for next game launch...{NC}\n")

            time.sleep(3)

    except KeyboardInterrupt:
        if is_gaming and suspended_processes:
            print(f"\n{YELLOW}[!] Exiting... Resuming all suspended processes.{NC}")
            resume_apps(suspended_processes)
        print(f"{CYAN}[*] Game Session Guard stopped.{NC}")

def main():
    parser = argparse.ArgumentParser(description="Game Session Guard - Automatic System Resource Optimizer")
    parser.add_argument("-run", "--start", action="store_true", help="Start background monitoring daemon")
    
    args = parser.parse_args()

    if args.start or len(sys.argv) == 1:
        monitor_session()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
