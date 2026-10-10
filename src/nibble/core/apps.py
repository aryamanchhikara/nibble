"""What kind of app is in front: decides cheering, focus streaks and quiet time.

Only the frontmost app's bundle id and name are used (from NSWorkspace, no
permissions). Websites inside a browser are invisible to us, so a browser is
just "browser".
"""

from __future__ import annotations

from enum import Enum


class Category(Enum):
    CODING = "coding"
    TERMINAL = "terminal"
    WRITING = "writing"
    SOCIAL = "social"
    VIDEO = "video"
    CALL = "call"
    BROWSER = "browser"
    OTHER = "other"


# Time in these counts toward a focus streak.
PRODUCTIVE = frozenset({Category.CODING, Category.TERMINAL, Category.WRITING})
# Switching to these ends a focus streak.
DISTRACTING = frozenset({Category.SOCIAL, Category.VIDEO, Category.CALL})

_BY_BUNDLE: dict[str, Category] = {}


def _add(category: Category, *bundle_ids: str) -> None:
    for b in bundle_ids:
        _BY_BUNDLE[b.lower()] = category


_add(
    Category.CODING,
    "com.microsoft.VSCode",
    "com.microsoft.VSCodeInsiders",
    "com.visualstudio.code.oss",
    "com.vscodium",
    "com.todesktop.230313mzl4w4u92",  # Cursor
    "com.exafunction.windsurf",
    "dev.zed.Zed",
    "dev.zed.Zed-Preview",
    "com.apple.dt.Xcode",
    "com.google.android.studio",
    "com.sublimetext.4",
    "com.sublimetext.3",
    "com.panic.Nova",
    "com.barebones.bbedit",
    "org.vim.MacVim",
    "org.gnu.Emacs",
    "com.github.GitHubClient",
    "com.sublimemerge",
    "com.fournova.Tower3",
)
_add(
    Category.TERMINAL,
    "com.apple.Terminal",
    "com.googlecode.iterm2",
    "dev.warp.Warp-Stable",
    "dev.warp.Warp",
    "com.mitchellh.ghostty",
    "io.alacritty",
    "org.alacritty",
    "net.kovidgoyal.kitty",
    "com.github.wez.wezterm",
    "co.zeit.hyper",
    "org.tabby",
)
_add(
    Category.WRITING,
    "com.apple.iWork.Pages",
    "com.microsoft.Word",
    "com.apple.TextEdit",
    "com.apple.Notes",
    "notion.id",
    "md.obsidian",
    "net.shinyfrog.bear",
    "com.ulyssesapp.mac",
    "pro.writer.mac",
    "com.literatureandlatte.scrivener3",
    "abnerworks.Typora",
    "com.lukilabs.lukiapp",  # Craft
    "com.quoteunquoteapps.highland2",
    "com.finaldraft.finaldraft.v12",
)
_add(
    Category.SOCIAL,
    "com.hnc.Discord",
    "com.apple.MobileSMS",
    "net.whatsapp.WhatsApp",
    "desktop.WhatsApp",
    "ru.keepcoder.Telegram",
    "org.telegram.desktop",
    "com.facebook.archon",
    "com.atebits.Tweetie2",
    "com.twitter.twitter-mac",
    "com.zhiliaoapp.musically",  # TikTok (iPhone app on Apple Silicon)
    "com.burbn.instagram",
    "com.burbn.barcelona",  # Threads
    "xyz.blueskyweb.app",
    "com.tapbots.Ivory",
    "com.reddit.Reddit",
)
_add(
    Category.VIDEO,
    "com.apple.TV",
    "com.apple.QuickTimePlayerX",
    "com.colliderli.iina",
    "org.videolan.vlc",
    "com.firecore.infuse",
    "tv.plex.desktop",
    "com.netflix.Netflix",
)
_add(
    Category.CALL,
    "us.zoom.xos",
    "com.microsoft.teams2",
    "com.microsoft.teams",
    "com.apple.FaceTime",
    "com.cisco.webexmeetingsapp",
    "Cisco-Systems.Spark",
    "com.webex.meetingmanager",
    "com.skype.skype",
    "app.tuple.app",
)
_add(
    Category.BROWSER,
    "com.apple.Safari",
    "com.apple.SafariTechnologyPreview",
    "com.google.Chrome",
    "com.google.Chrome.canary",
    "org.mozilla.firefox",
    "company.thebrowser.Browser",  # Arc
    "com.brave.Browser",
    "com.microsoft.edgemac",
    "com.operasoftware.Opera",
    "com.vivaldi.Vivaldi",
    "app.zen-browser.zen",
    "com.kagi.kagimacOS",  # Orion
)

# Whole families of apps that share a bundle-id prefix.
_PREFIXES = (("com.jetbrains.", Category.CODING),)

# Last resort for apps we don't know by bundle id.
_NAME_HINTS = (
    ("terminal", Category.TERMINAL),
    ("zoom", Category.CALL),
    ("code", Category.CODING),
)


def categorize(bundle_id: str | None, name: str | None = None) -> Category:
    if bundle_id:
        b = bundle_id.lower()
        if b in _BY_BUNDLE:
            return _BY_BUNDLE[b]
        for prefix, category in _PREFIXES:
            if b.startswith(prefix):
                return category
    if name:
        n = name.lower()
        for hint, category in _NAME_HINTS:
            if hint in n:
                return category
    return Category.OTHER
