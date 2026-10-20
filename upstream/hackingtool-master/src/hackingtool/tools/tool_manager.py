import os
import subprocess

from rich.prompt import Confirm

from hackingtool.core import HackingTool, HackingToolsCollection, console
from hackingtool.constants import USER_CONFIG_DIR, REPO_WEB_URL


class UpdateTool(HackingTool):
    TITLE = "Update Tool or System"
    DESCRIPTION = "Update system packages or pull the latest hackingtool code"

    def __init__(self):
        super().__init__([
            ("Update System", self.update_sys),
            ("Update Hackingtool", self.update_ht),
        ], installable=False, runnable=False)

    def update_sys(self):
        from hackingtool.os_detect import CURRENT_OS, PACKAGE_UPDATE_CMDS
        mgr = CURRENT_OS.pkg_manager
        cmd = PACKAGE_UPDATE_CMDS.get(mgr)
        if cmd:
            priv = "" if (CURRENT_OS.system == "macos" or os.geteuid() == 0) else "sudo "
            # shell=True needed — cmd contains && chains; strings are hardcoded, not user input
            subprocess.run(f"{priv}{cmd}", shell=True, check=False)
        else:
            console.print("[warning]Unknown package manager — update manually.[/warning]")

    def update_ht(self):
        # hackingtool ships as a standard package (pipx/pip/.deb/docker). It can't
        # reliably self-update its own installed package from inside, so show the
        # right command for each channel instead of a broken git-pull.
        console.print("[bold cyan]Update hackingtool with the command for how you installed it:[/bold cyan]")
        console.print("  pipx     [success]pipx upgrade hackingtool[/success]")
        console.print("  pip      [success]pip install --upgrade hackingtool[/success]")
        console.print("  .deb     download the latest .deb, then [success]sudo apt install ./<file>.deb[/success]")
        console.print("  docker   [success]docker pull hardikzinzu/hackingtool:latest[/success]")
        console.print(f"[dim]Latest release: {REPO_WEB_URL}/releases/latest[/dim]")


class UninstallTool(HackingTool):
    TITLE = "Uninstall HackingTool"
    DESCRIPTION = "Remove hackingtool from system"

    def __init__(self):
        super().__init__([
            ("Uninstall", self.uninstall),
        ], installable=False, runnable=False)

    def uninstall(self):
        import shutil
        # Remove the package itself with the channel's own command (we can't
        # uninstall our own pipx/pip/apt package from inside it). We can clean up
        # the one thing we own regardless of install method: the ~/.hackingtool data.
        console.print("[warning]Remove the hackingtool package with the command for how you installed it:[/warning]")
        console.print("  pipx     [success]pipx uninstall hackingtool[/success]")
        console.print("  pip      [success]pip uninstall hackingtool[/success]")
        console.print("  .deb     [success]sudo apt remove python3-hackingtool[/success]")
        console.print("  docker   [success]docker rmi hardikzinzu/hackingtool:latest[/success]")

        if USER_CONFIG_DIR.exists() and Confirm.ask(
                f"Remove your data + installed tools at {USER_CONFIG_DIR} now?", default=False):
            shutil.rmtree(str(USER_CONFIG_DIR), ignore_errors=True)
            console.print(f"[success]✔ Removed {USER_CONFIG_DIR}[/success]")


class ToolManager(HackingToolsCollection):
    TITLE = "Update or Uninstall | Hackingtool"
    TOOLS = [
        UpdateTool(),
        UninstallTool(),
    ]


if __name__ == "__main__":
    manager = ToolManager()
    manager.show_options()
