#!/usr/bin/env python3
"""
game-session-guard - Automatic FPS & System Resource Optimizer
License: MIT
"""

import os
import sys
import time
import json
import re
import psutil
import argparse
import signal
import subprocess
import pwd
from pathlib import Path

# Terminal colors
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
CYAN = '\033[0;36m'
NC = '\033[0m'

def _session_home():
    sudo_user = os.environ.get("SUDO_USER") if os.geteuid() == 0 else None
    if sudo_user:
        try:
            return Path(pwd.getpwnam(sudo_user).pw_dir)
        except KeyError:
            pass
    return Path.home()

SESSION_HOME = _session_home()
USER_CONFIG_PATH = SESSION_HOME / ".config" / "game-session-guard" / "config.json"
SYSTEM_CONFIG_PATH = Path("/etc/game-session-guard/config.json")

DEFAULT_CONFIG = {
    "target_games": [
        "minecraft", "csgo", "cs2", "dota2", "fortnite", "valorant", "roblox",
        "gta5", "cyberpunk2077", "witcher3", "apex", "pubg", "genshinimpact",
        "eldenring", "bg3", "baldursgate3", "stardewvalley", "terraria", "factorio",
        "palworld", "helldivers2", "eldenring", "hades2", "overwatch", "leagueoflegends",
        "warframe", "warthunder", "worldoftanks", "pathofexile", "diablo4", "rdr2",
        "minecraft", "csgo", "cs2", "dota2", "fortnite", "roblox",
        "vita3k", "rpcs3", "yuzu", "pcsx2", "ppsspp", "dolphin-emu", "retroarch"
    ],
    "apps_to_suspend": [
        "chrome", "chromium", "firefox", "zen", "brave", "opera", "vivaldi", "yandexbrowser", "edge",
        "telegram-desktop", "telegram", "discord", "vesktop", "webcord", "slack", "skype",
        "spotify", "vlc", "obs", "obs64", "qbittorrent", "transmission"
    ]
}

LAUNCHER_NAMES = {"steam", "steamwebhelper", "heroic", "lutris", "bottles", "portproton",
                  "galaxyclient", "epicgameslauncher", "battle.net", "ubisoftconnect", "eadesktop",
                  "java", "javaw", "wine", "wine64", "proton", "gamescope"}

def get_config_path():
    override = os.environ.get("GAMEGUARD_CONFIG")
    if override:
        return Path(override).expanduser()
    for path in (USER_CONFIG_PATH, SYSTEM_CONFIG_PATH, Path(__file__).parent / "config.json",
                 Path("/usr/local/bin/gameguard_config.json")):
        if path.exists():
            return path
    return USER_CONFIG_PATH

def load_config():
    path = get_config_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
    except (OSError, json.JSONDecodeError):
        user_cfg = {}
        use_custom_lists = user_cfg.get("replace_defaults", False)
        try:
            scan_interval = max(1, int(user_cfg.get("scan_interval", 3)))
        except (TypeError, ValueError):
            scan_interval = 3
    return {
        "target_games": sorted(set(user_cfg.get("target_games", []) if use_custom_lists else
                                   DEFAULT_CONFIG["target_games"] + user_cfg.get("target_games", []))),
        "apps_to_suspend": sorted(set(user_cfg.get("apps_to_suspend", []) if use_custom_lists else
                                       DEFAULT_CONFIG["apps_to_suspend"] + user_cfg.get("apps_to_suspend", []))),
        "suspend_apps": user_cfg.get("suspend_apps", True),
        "boost_priority": user_cfg.get("boost_priority", True),
        "drop_cache": user_cfg.get("drop_cache", False),
            "scan_interval": scan_interval,
    }

def save_config(config):
    path = Path(os.environ["GAMEGUARD_CONFIG"]).expanduser() if os.environ.get("GAMEGUARD_CONFIG") else USER_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

def _steam_roots():
    roots = [SESSION_HOME / ".steam/steam", SESSION_HOME / ".local/share/Steam",
             SESSION_HOME / ".var/app/com.valvesoftware.Steam/.local/share/Steam"]
    roots.extend(Path(path) for path in (os.environ.get("STEAM_DIR"),) if path)
    libraries = set()
    for root in roots:
        if (root / "steamapps").is_dir():
            libraries.add((root / "steamapps").resolve())
        vdf = root / "steamapps/libraryfolders.vdf"
        if vdf.is_file():
            try:
                content = vdf.read_text(encoding="utf-8", errors="ignore")
                for library in re.findall(r'"(?:path|[0-9]+)"\s+"([^"]+)"', content):
                    libraries.add((Path(library) / "steamapps").expanduser())
            except OSError:
                pass
    return libraries

def _acf_value(content, key):
    match = re.search(r'"' + re.escape(key) + r'"\s+"([^"]*)"', content)
    return match.group(1) if match else ""

def discover_steam_games():
    """Return installed games from every Steam library known to this user."""
    games = {}
    for steamapps in _steam_roots():
        try:
            manifests = steamapps.glob("appmanifest_*.acf")
            for manifest in manifests:
                content = manifest.read_text(encoding="utf-8", errors="ignore")
                name = _acf_value(content, "name")
                app_id = _acf_value(content, "appid")
                install_dir = _acf_value(content, "installdir")
                if name and install_dir:
                    game_path = steamapps / "common" / install_dir
                    games[app_id or str(game_path)] = {
                        "name": name, "appid": app_id, "path": str(game_path)
                    }
        except OSError:
            continue
    return sorted(games.values(), key=lambda game: game["name"].casefold())

def _normalize_name(value):
    return re.sub(r"[^a-z0-9]", "", value.casefold())

def _session_uid():
    if os.geteuid() == 0 and os.environ.get("SUDO_UID", "").isdigit():
        return int(os.environ["SUDO_UID"])
    return os.getuid() if hasattr(os, "getuid") else None

def is_heuristic_game(proc, steam_games=()) -> bool:
    """Recognize game processes by their installed game directory, not launchers."""
    try:
        proc_name = (proc.info.get("name") or proc.name()).casefold()
        if proc_name in LAUNCHER_NAMES:
            return False
        locations = [proc.exe() or ""] + proc.cmdline()
        for game in steam_games:
            game_path = game["path"].casefold()
            if any(game_path in location.casefold() for location in locations if location):
                return True
        command = " ".join(locations).casefold()
        if any(indicator in command for indicator in ("/heroic/games/", "/lutris/games/")):
            return not any(name in command for name in ("chrome", "firefox", "telegram", "systemd"))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return False

def find_running_targets(target_names, steam_games=()):
    running = []
    names = {_normalize_name(name) for name in target_names} - {_normalize_name(name) for name in LAUNCHER_NAMES}
    session_uid = _session_uid()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'exe']):
        try:
            if session_uid is not None and proc.uids().real != session_uid:
                continue
            p_name = _normalize_name(proc.info.get('name') or "")
            is_matched = (p_name in names or is_heuristic_game(proc, steam_games))
            if is_matched:
                running.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return running

def get_apps_to_suspend(app_names, excluded_pids=()):
    procs = []
    current_pid = os.getpid()
    current_uid = _session_uid()
    names = {_normalize_name(name) for name in app_names}
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if proc.info['pid'] == current_pid:
                continue
            if proc.pid in excluded_pids or (current_uid is not None and proc.uids().real != current_uid):
                continue
            p_name = _normalize_name(proc.info.get('name') or "")
            if p_name in names:
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
    steam_games = discover_steam_games()

    try:
        while True:
            running_games = find_running_targets(target_games, steam_games)

            if running_games and not is_gaming:
                is_gaming = True
                game_names = ", ".join(set(p.name() for p in running_games))
                print(f"{GREEN}[!] Game detected: {game_names}{NC}")
                print(f"{CYAN}[*] Optimizing system for peak FPS...{NC}")

                # Free system RAM cache
                if config["drop_cache"]:
                    drop_system_cache()

                # Boost priority
                if config["boost_priority"]:
                    boost_game_priority(running_games)

                # Suspend background applications
                game_pids = {proc.pid for proc in running_games}
                suspended_processes = get_apps_to_suspend(apps_to_suspend, game_pids) if config["suspend_apps"] else []
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

            time.sleep(config["scan_interval"])

    except KeyboardInterrupt:
        if is_gaming and suspended_processes:
            print(f"\n{YELLOW}[!] Exiting... Resuming all suspended processes.{NC}")
            resume_apps(suspended_processes)
        print(f"{CYAN}[*] Game Session Guard stopped.{NC}")

def launch_gui():
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
    except ImportError:
        print("Tkinter is unavailable. Install your distribution's python3-tk package.", file=sys.stderr)
        return

    config = load_config()
    monitor = {"process": None}
    palette = {"background": "#101719", "surface": "#192326", "raised": "#223034",
               "text": "#edf3ef", "muted": "#9aaba8", "accent": "#8de0b1",
               "accent_dark": "#345e4a", "border": "#344447"}
    root = tk.Tk()
    root.title("Game Session Guard")
    root.geometry("1080x780")
    root.minsize(880, 650)
    root.configure(bg=palette["background"])
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("Treeview", background=palette["surface"], fieldbackground=palette["surface"],
                    foreground=palette["text"], rowheight=27, borderwidth=0)
    style.configure("Treeview.Heading", background=palette["raised"], foreground=palette["muted"],
                    relief="flat", font=("TkDefaultFont", 9, "bold"))
    style.map("Treeview", background=[("selected", palette["accent_dark"])])

    def label(parent, text, size=10, color=None, bold=False):
        return tk.Label(parent, text=text, bg=parent["bg"], fg=color or palette["text"],
                        font=("TkDefaultFont", size, "bold" if bold else "normal"))

    def button(parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command, bg=palette["accent"] if primary else palette["raised"],
                         fg=palette["background"] if primary else palette["text"], activebackground=palette["accent_dark"],
                         activeforeground=palette["text"], relief="flat", bd=0, padx=14, pady=8,
                         font=("TkDefaultFont", 9, "bold"), cursor="hand2")

    header = tk.Frame(root, bg=palette["background"], padx=24, pady=20)
    header.pack(fill="x")
    label(header, "GAME SESSION GUARD", 17, palette["accent"], True).pack(anchor="w")
    label(header, "Session controls  /  Steam library  /  background workload", 10, palette["muted"]).pack(anchor="w", pady=(5, 0))

    body = tk.Frame(root, bg=palette["background"], padx=24)
    body.pack(fill="both", expand=True)
    columns = tk.Frame(body, bg=palette["background"])
    columns.pack(fill="both", expand=True)
    columns.columnconfigure(0, weight=1, uniform="column")
    columns.columnconfigure(1, weight=1, uniform="column")

    def list_panel(parent, title, values, column):
        panel = tk.Frame(parent, bg=palette["surface"], padx=14, pady=13,
                         highlightthickness=1, highlightbackground=palette["border"])
        panel.grid(row=0, column=column, sticky="nsew", padx=(0, 7) if column == 0 else (7, 0))
        label(panel, title, 11, bold=True).pack(anchor="w", pady=(0, 10))
        listbox = tk.Listbox(panel, selectmode=tk.EXTENDED, height=12, bg=palette["background"],
                             fg=palette["text"], selectbackground=palette["accent_dark"],
                             highlightthickness=0, relief="flat", activestyle="none",
                             font=("TkFixedFont", 9))
        listbox.pack(fill="both", expand=True)
        for value in values:
            listbox.insert(tk.END, value)
        controls = tk.Frame(panel, bg=palette["surface"])
        controls.pack(fill="x", pady=(9, 0))
        entry = tk.Entry(controls, bg=palette["background"], fg=palette["text"],
                         insertbackground=palette["text"], relief="flat", font=("TkDefaultFont", 10))
        entry.pack(side="left", fill="x", expand=True, ipady=7, padx=(0, 7))

        def add_item():
            value = entry.get().strip()
            current = {listbox.get(index).casefold() for index in range(listbox.size())}
            if value and value.casefold() not in current:
                listbox.insert(tk.END, value)
            entry.delete(0, tk.END)

        def remove_items():
            for index in reversed(listbox.curselection()):
                listbox.delete(index)

        button(controls, "Add", add_item).pack(side="left", padx=(0, 5))
        button(controls, "Remove", remove_items).pack(side="left")
        return listbox

    targets_list = list_panel(columns, "GAME PROCESS NAMES", config["target_games"], 0)
    apps_list = list_panel(columns, "BACKGROUND APPS", config["apps_to_suspend"], 1)

    library_panel = tk.Frame(body, bg=palette["surface"], padx=14, pady=12,
                             highlightthickness=1, highlightbackground=palette["border"])
    library_panel.pack(fill="both", expand=True, pady=(14, 0))
    library_header = tk.Frame(library_panel, bg=palette["surface"])
    library_header.pack(fill="x", pady=(0, 8))
    label(library_header, "INSTALLED STEAM LIBRARY", 11, bold=True).pack(side="left")
    game_count = label(library_header, "", 9, palette["muted"])
    game_count.pack(side="right")
    tree = ttk.Treeview(library_panel, columns=("appid", "location"), show="tree headings", height=8)
    tree.heading("#0", text="Game")
    tree.heading("appid", text="APP ID")
    tree.heading("location", text="Install directory")
    tree.column("#0", width=240, minwidth=150)
    tree.column("appid", width=90, minwidth=75, stretch=False)
    tree.column("location", width=420, minwidth=150)
    tree.pack(fill="both", expand=True)
    steam_library = []

    def refresh_library():
        nonlocal steam_library
        steam_library = discover_steam_games()
        tree.delete(*tree.get_children())
        for game in steam_library:
            tree.insert("", tk.END, text=game["name"], values=(game["appid"], game["path"]))
        game_count.config(text=f"{len(steam_library)} installed games · auto-detected")

    def add_selected_steam_game(event=None):
        if event is not None:
            clicked_row = tree.identify_row(event.y)
            if clicked_row:
                tree.selection_set(clicked_row)
        selected = tree.selection()
        if not selected:
            return
        game_name = tree.item(selected[0], "text")
        existing = {targets_list.get(i).casefold() for i in range(targets_list.size())}
        if game_name.casefold() not in existing:
            targets_list.insert(tk.END, game_name)

    tree.bind("<Double-1>", add_selected_steam_game)
    refresh_library()

    options = tk.Frame(body, bg=palette["background"])
    options.pack(fill="x", pady=(12, 7))
    suspend_var = tk.BooleanVar(value=config["suspend_apps"])
    priority_var = tk.BooleanVar(value=config["boost_priority"])
    cache_var = tk.BooleanVar(value=config["drop_cache"])
    for text, variable in (("Suspend selected background apps", suspend_var),
                           ("Raise game priority", priority_var), ("Clear kernel cache", cache_var)):
        tk.Checkbutton(options, text=text, variable=variable, bg=palette["background"],
                       fg=palette["text"], activebackground=palette["background"],
                       activeforeground=palette["accent"], selectcolor=palette["surface"],
                       font=("TkDefaultFont", 9)).pack(side="left", padx=(0, 18))

    footer = tk.Frame(root, bg=palette["surface"], padx=24, pady=13)
    footer.pack(fill="x", side="bottom")
    status = tk.StringVar(value="Ready · no monitor running")
    label(footer, "", 9).pack(side="left")
    status_label = tk.Label(footer, textvariable=status, bg=palette["surface"], fg=palette["muted"],
                            font=("TkDefaultFont", 9))
    status_label.pack(side="left", fill="x", expand=True)

    def save_settings():
        saved = {
            "target_games": [targets_list.get(i) for i in range(targets_list.size())],
            "apps_to_suspend": [apps_list.get(i) for i in range(apps_list.size())],
            "replace_defaults": True,
            "suspend_apps": suspend_var.get(), "boost_priority": priority_var.get(),
            "drop_cache": cache_var.get(), "scan_interval": config["scan_interval"],
        }
        try:
            save_config(saved)
            config.update(saved)
            status.set(f"Settings saved · {get_config_path()}")
        except OSError as error:
            messagebox.showerror("Could not save settings", str(error), parent=root)

    def stop_monitor():
        process = monitor["process"]
        if process and process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.terminate()
            status.set("Monitor stopped")
        monitor["process"] = None
        start_button.config(state=tk.NORMAL)
        stop_button.config(state=tk.DISABLED)

    def start_monitor():
        if monitor["process"] and monitor["process"].poll() is None:
            return
        save_settings()
        monitor["process"] = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--start"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        status.set("Monitoring · waiting for a game")
        start_button.config(state=tk.DISABLED)
        stop_button.config(state=tk.NORMAL)

    actions = tk.Frame(footer, bg=palette["surface"])
    actions.pack(side="right")
    button(actions, "Refresh library", refresh_library).pack(side="left", padx=(0, 7))
    button(actions, "Save settings", save_settings).pack(side="left", padx=(0, 7))
    start_button = button(actions, "Start monitor", start_monitor, primary=True)
    start_button.pack(side="left", padx=(0, 7))
    stop_button = button(actions, "Stop", stop_monitor)
    stop_button.pack(side="left")
    stop_button.config(state=tk.DISABLED)

    def update_status():
        process = monitor["process"]
        if process and process.poll() is not None:
            status.set(f"Monitor exited · code {process.returncode}")
            monitor["process"] = None
            start_button.config(state=tk.NORMAL)
            stop_button.config(state=tk.DISABLED)
        root.after(1000, update_status)

    def close_window():
        stop_monitor()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close_window)
    update_status()
    root.mainloop()

def main():
    parser = argparse.ArgumentParser(description="Game Session Guard - Automatic System Resource Optimizer")
    parser.add_argument("-run", "--start", action="store_true", help="Start background monitoring daemon")
    parser.add_argument("--gui", action="store_true", help="Open the settings dashboard")
    
    args = parser.parse_args()

    if args.gui:
        launch_gui()
    elif args.start or len(sys.argv) == 1:
        monitor_session()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
