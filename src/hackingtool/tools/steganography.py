import subprocess

from hackingtool.core import HackingTool, HackingToolsCollection, console
from hackingtool.core import validate_input

from rich.panel import Panel
from rich.prompt import Prompt


class SteganoHide(HackingTool):
    TITLE = "SteganoHide"
    INSTALL_COMMANDS = ["sudo apt-get install steghide -y"]

    def run(self):
        choice_run = input(
            "[1] Hide\n"
            "[2] Extract\n"
            "[99]Cancel\n"
            ">> "
        )
        choice_run = validate_input(choice_run, [1, 2, 99])
        if choice_run is None:
            console.print("[bold red]Please choose a valid input[/bold red]")
            return self.run()

        if choice_run == 99:
            return

        if choice_run == 1:
            file_hide = input("Enter Filename to Embed (1.txt) >> ")
            file_to_be_hide = input("Enter Cover Filename (test.jpeg) >> ")
            if not file_hide.strip() or not file_to_be_hide.strip():
                console.print("[bold red]Both filenames are required[/bold red]")
                return
            subprocess.run(["steghide", "embed", "-cf", file_to_be_hide, "-ef", file_hide])

        elif choice_run == 2:
            from_file = input("Enter Filename to Extract Data From >> ")
            if not from_file.strip():
                console.print("[bold red]A filename is required[/bold red]")
                return
            subprocess.run(["steghide", "extract", "-sf", from_file])


class StegnoCracker(HackingTool):
    TITLE = "Stegseek (fast steganography cracker)"
    DESCRIPTION = "Stegseek brute-forces and extracts steghide-embedded data extremely fast"
    INSTALL_COMMANDS = ["sudo apt-get install -y stegseek"]
    RUN_COMMANDS = ["stegseek --help"]
    PROJECT_URL = "https://github.com/RickdeJager/stegseek"
    SYSTEM_PKGS = {"which": "stegseek", "apt": "stegseek"}


class StegoCracker(HackingTool):
    ARCHIVED = True
    ARCHIVED_REASON = "Unmaintained — no commits since 2021-09"
    TITLE = "StegoCracker"
    DESCRIPTION = "StegoCracker lets you hide and retrieve data in image or audio files"
    INSTALL_COMMANDS = [
        "git clone https://github.com/W1LDN16H7/StegoCracker.git",
        "sudo chmod -R 755 StegoCracker"
    ]
    RUN_COMMANDS = [
        "cd StegoCracker && python3 -m pip install -r requirements.txt",
        "./install.sh"
    ]
    PROJECT_URL = "https://github.com/W1LDN16H7/StegoCracker"


class Whitespace(HackingTool):
    ARCHIVED = True
    ARCHIVED_REASON = "Upstream repo deleted (404)"
    TITLE = "Whitespace"
    DESCRIPTION = "Use whitespace and unicode characters for steganography"
    INSTALL_COMMANDS = [
        "git clone https://github.com/beardog108/snow10.git",
        "sudo chmod -R 755 snow10"
    ]
    RUN_COMMANDS = ["cd snow10 && ./install.sh"]
    PROJECT_URL = "https://github.com/beardog108/snow10"


class SteganographyTools(HackingToolsCollection):
    TITLE = "Steganography Tools"
    TOOLS = [SteganoHide(), StegnoCracker(), StegoCracker(), Whitespace()]

if __name__ == "__main__":
    tools = SteganographyTools()
    tools.show_options()
