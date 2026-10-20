from hackingtool.core import HackingTool, HackingToolsCollection, console

from rich.panel import Panel
from rich.prompt import Prompt


class KnockMail(HackingTool):
    ARCHIVED = True
    ARCHIVED_REASON = "Unmaintained — no commits since 2021-12"
    TITLE = "Knockmail"
    DESCRIPTION = "KnockMail Tool Verify If Email Exists"
    INSTALL_COMMANDS = [
        "git clone https://github.com/heywoodlh/KnockMail.git",
        "cd KnockMail;sudo pip3 install -r requirements.txt"
    ]
    RUN_COMMANDS = ["cd KnockMail;python3 knockmail.py"]
    PROJECT_URL = "https://github.com/heywoodlh/KnockMail"


class EmailVerifyTools(HackingToolsCollection):
    TITLE = "Email Verify tools"
    TOOLS = [KnockMail()]

if __name__ == "__main__":
    tools = EmailVerifyTools()
    tools.show_options()
