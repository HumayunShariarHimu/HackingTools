import os
import subprocess

from hackingtool.core import HackingTool, HackingToolsCollection, console
from hackingtool.tools.others.android_attack import AndroidAttackTools
from hackingtool.tools.others.email_verifier import EmailVerifyTools
from hackingtool.tools.others.hash_crack import HashCrackingTools
from hackingtool.tools.others.homograph_attacks import IDNHomographAttackTools
from hackingtool.tools.others.mix_tools import MixTools
from hackingtool.tools.others.payload_injection import PayloadInjectorTools
from hackingtool.tools.others.socialmedia import SocialMediaBruteforceTools
from hackingtool.tools.others.socialmedia_finder import SocialMediaFinderTools
from hackingtool.tools.others.web_crawling import WebCrawlingTools
from hackingtool.tools.others.wifi_jamming import WifiJammingTools

from rich.panel import Panel
from rich.prompt import Prompt


class HatCloud(HackingTool):
    TITLE = "HatCloud(Bypass CloudFlare for IP)"
    DESCRIPTION = "HatCloud build in Ruby. It makes bypass in CloudFlare for " \
                  "discover real IP."
    INSTALL_COMMANDS = ["git clone https://github.com/HatBashBR/HatCloud.git"]
    PROJECT_URL = "https://github.com/HatBashBR/HatCloud"

    def run(self):
        from hackingtool.config import get_tools_dir
        from rich.prompt import Prompt
        site = Prompt.ask("Enter Site")
        # Bug 3 fix: os.chdir() replaced with cwd= parameter
        subprocess.run(
            ["sudo", "ruby", "hatcloud.rb", "-b", site],
            cwd=str(get_tools_dir() / "HatCloud"),
        )


class OtherTools(HackingToolsCollection):
    TITLE = "Other tools"
    TOOLS = [
        SocialMediaBruteforceTools(),
        AndroidAttackTools(),
        HatCloud(),
        IDNHomographAttackTools(),
        EmailVerifyTools(),
        HashCrackingTools(),
        WifiJammingTools(),
        SocialMediaFinderTools(),
        PayloadInjectorTools(),
        WebCrawlingTools(),
        MixTools()
    ]

if __name__ == "__main__":
    tools = OtherTools()
    tools.show_options()
