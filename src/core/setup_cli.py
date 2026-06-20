from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def parse_parallels_vms() -> list[dict[str, str]]:
    """Execute 'prlctl list --all' and parse VM info."""
    prlctl_path = shutil.which("prlctl")
    if not prlctl_path:
        return []

    try:
        output = subprocess.check_output([prlctl_path, "list", "--all"], text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return []

    vms = []
    lines = output.strip().splitlines()
    if len(lines) <= 1:
        return []

    # Header looks like: UUID STATUS IP_ADDR NAME
    # Skip header
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 4:
            uuid = parts[0]
            status = parts[1]
            ip = parts[2]
            name = " ".join(parts[3:])
            vms.append({"uuid": uuid, "status": status, "ip": ip, "name": name})
        elif len(parts) == 3:
            uuid = parts[0]
            status = parts[1]
            name = parts[2]
            vms.append({"uuid": uuid, "status": status, "ip": "-", "name": name})
    return vms


def check_windows_env() -> dict[str, Any]:
    """Check native Windows environment dependencies."""
    results = {"pywin32": False, "visio": False}
    try:
        import win32com.client
        results["pywin32"] = True
        try:
            import pythoncom
            pythoncom.CoInitialize()
            clsid = pythoncom.CLSIDFromProgID("Visio.Application")
            if clsid:
                results["visio"] = True
            pythoncom.CoUninitialize()
        except Exception:
            pass
    except ImportError:
        pass
    return results


def run_setup(non_interactive: bool = False, output_dir: str | None = None) -> int:
    print("=" * 60)
    print("               Visio Bridge Environment Setup")
    print("=" * 60)

    current_os = platform.system()
    print(f"[*] Detected Host OS: {current_os}")

    config: dict[str, Any] = {
        "backend": "auto",
        "desktop_transport_mode": "auto",
        "vm_name": "",
        "visible": False,
        "timeout": 180
    }

    is_interactive = not non_interactive and sys.stdin.isatty()

    vms = []
    if current_os == "Darwin":
        print("[*] Detecting macOS Parallels Desktop VM configuration...")
        vms = parse_parallels_vms()
        if vms:
            print(f"[+] Found {len(vms)} registered Parallels VM(s):")
            for i, vm in enumerate(vms, 1):
                print(f"    {i}. {vm['name']} (Status: {vm['status']})")
            
            # Select default VM (prefer running ones, or default to first one)
            running_vms = [vm for vm in vms if vm["status"] == "running"]
            default_vm = running_vms[0]["name"] if running_vms else vms[0]["name"]
            config["vm_name"] = default_vm
            config["desktop_transport_mode"] = "parallels"
        else:
            print("[-] No Parallels VMs detected (or 'prlctl' not available).")
            config["desktop_transport_mode"] = "auto"
    elif current_os == "Windows":
        print("[*] Detecting Windows native COM automation requirements...")
        env = check_windows_env()
        if env["pywin32"]:
            print("[+] pywin32 is installed.")
            config["desktop_transport_mode"] = "windows-local"
            if env["visio"]:
                print("[+] Microsoft Visio is registered via COM.")
            else:
                print("[!] Microsoft Visio is not detected as registered via COM. Please ensure Visio is installed.")
        else:
            print("[-] pywin32 is NOT installed. Run 'pip install pywin32' or 'pip install -e .[desktop]' to install.")
            config["desktop_transport_mode"] = "auto"
    elif current_os == "Linux":
        print("[*] Detected Linux host. Visio Desktop is not natively supported.")
        print("[+] Defaulting default backend to 'xml'.")
        config["backend"] = "xml"
        config["desktop_transport_mode"] = "auto"
    else:
        print(f"[*] Detected OS {current_os}. Defaulting default backend to 'xml'.")
        config["backend"] = "xml"
        config["desktop_transport_mode"] = "auto"

    # Interactive inputs
    if is_interactive:
        # 1. Choose Backend
        print("\n--- Step 1: Select Default Backend ---")
        print("1. auto    - (Recommended) Prefer Desktop COM automation if available, fall back to XML ZIP.")
        print("2. xml     - Fast, pure XML ZIP file writer (cross-platform, no Visio required).")
        print("3. desktop - Require Visio Desktop COM automation (Windows or Parallels VM).")
        
        while True:
            choice = input("Select choice [1-3] (default: 1/auto): ").strip()
            if not choice:
                config["backend"] = "auto"
                break
            if choice == "1":
                config["backend"] = "auto"
                break
            elif choice == "2":
                config["backend"] = "xml"
                break
            elif choice == "3":
                config["backend"] = "desktop"
                break
            print("Invalid choice, please select 1, 2, or 3.")

        # 2. Select VM name (if on macOS and VMs are found)
        if current_os == "Darwin" and vms:
            print("\n--- Step 2: Configure Parallels VM for Visio automation ---")
            print(f"Detected default VM: '{config['vm_name']}'")
            use_default = input(f"Use default VM name '{config['vm_name']}'? [Y/n]: ").strip().lower()
            if use_default == "n":
                print("Registered VMs:")
                for i, vm in enumerate(vms, 1):
                    print(f"  {i}. {vm['name']}")
                print("  0. Specify custom VM name")
                
                while True:
                    vm_choice = input(f"Select choice [0-{len(vms)}]: ").strip()
                    if not vm_choice:
                        break
                    try:
                        idx = int(vm_choice)
                        if 1 <= idx <= len(vms):
                            config["vm_name"] = vms[idx - 1]["name"]
                            break
                        elif idx == 0:
                            custom_name = input("Enter custom VM name: ").strip()
                            if custom_name:
                                config["vm_name"] = custom_name
                                break
                    except ValueError:
                        pass
                    print(f"Invalid choice, please enter 0 to {len(vms)}.")

        # 3. Timeout and Visibility
        print("\n--- Step 3: Desktop Automation Settings ---")
        visible_input = input("Should the Visio Desktop window be visible during automation? [y/N]: ").strip().lower()
        config["visible"] = (visible_input == "y")
        
        timeout_input = input("Timeout for desktop operations in seconds (default: 180): ").strip()
        if timeout_input:
            try:
                config["timeout"] = int(timeout_input)
            except ValueError:
                print("[!] Invalid timeout value, using default (180s).")

    else:
        print("\n[*] Non-interactive mode: applying auto-detected defaults.")

    # Write configuration
    target_dir = Path(output_dir) if output_dir else Path(os.getcwd())
    config_file = target_dir / ".visio_bridge.json"
    
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        print(f"\n[+] Configuration file successfully written to: {config_file}")
        print("Generated settings:")
        print(json.dumps(config, indent=2))
        print("=" * 60)
        return 0
    except Exception as exc:
        print(f"\n[!] Failed to write configuration file: {exc}", file=sys.stderr)
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Setup configuration for Visio Bridge.")
    parser.add_argument("--non-interactive", action="store_true", help="Run setup in non-interactive mode.")
    parser.add_argument("--output-dir", type=str, default=None, help="Directory to save the .visio_bridge.json config file.")
    args = parser.parse_args()
    
    sys.exit(run_setup(non_interactive=args.non_interactive, output_dir=args.output_dir))


if __name__ == "__main__":
    main()
