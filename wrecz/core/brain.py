"""
Wrecz conversational Brain.

This is the single replacement for core/brain.py.
It preserves the existing deterministic controls and JSON command
contract while adding short-term conversational context.
"""

import json
import re
import requests

try:
    from .conversation import STATE
except ImportError:
    from conversation import STATE


# =========================================================
# WRECZ BRAIN
# =========================================================

OLLAMA_URL = "http://localhost:11434/api/chat"

MODEL = "wrecz-brain"

# How long Ollama keeps the classifier in memory after a request.
#
# The model is ~2.5 GB. Loading it costs about 10 seconds, which the user
# pays on the first command after any idle gap, so it is kept resident.
# Set this to a duration such as "30m" to hand the memory back instead.
#
# Ollama wants a number of seconds or a duration string; -1 means "never
# unload". It must be the integer, not the string "-1", which the API
# rejects with a 400.
KEEP_ALIVE = -1


# =========================================================
# INTENT CLASSIFIER PROMPT
# =========================================================

CLASSIFIER_PROMPT = """
You are the intent classifier for Wrecz, a Windows PC assistant.

Your only job is to read the user's message and decide which ONE action the
Wrecz controller should carry out. An external controller performs the action;
you only name it.

DECIDING BETWEEN ACTION AND CONVERSATION

This is the decision you get wrong most often, so apply it literally.

Use "conversation" ONLY when the user is not asking for anything to be done:
  - greetings and small talk               "hi", "how are you", "thanks"
  - questions about you                    "who are you", "what can you do"
  - opinions and chat                      "tell me a joke", "what do you think"

If the user is asking for something to HAPPEN, it is never "conversation",
even when phrased politely or as a question. "Can you search for X" is a
request to search, not a question about your abilities.

WEB SEARCH

Any request to search, google, look up, browse, or find something on the
internet is "web_search". Put ONLY the thing being searched for in "target" -
no "search for", no "please", no question mark.

Also use "web_search" for questions needing current information you cannot
know: weather, news, prices, scores, "latest", "today".

Do NOT answer these yourself with "conversation". Searching is a normal,
expected Wrecz action.

TARGETS

"target" must contain only the object of the action, cleaned up:
  "please open google chrome"        -> open_application, target "google chrome"
  "can you search for cheap flights" -> web_search,       target "cheap flights"
  "turn the volume down a bit"       -> volume_decrease,  target "10"

Leave "target" empty when the action needs none.

CONTEXT

Use the previous conversation to resolve "it", "that", "again", "instead",
"a bit more". Never ask for a number just because a relative change was
requested; a plain "louder" or "brighter" means the default amount of 10.
Only require an exact percentage when the user explicitly asks for one.

Use "clarification" ONLY when you genuinely cannot tell what is being asked.
Use "unsupported" ONLY for a real Wrecz capability that does not exist.
Never invent a capability, and never expose JSON, intents or internal terms
to the user.

ALLOWED INTENTS

open_application, close_application,
volume_set, volume_increase, volume_decrease, volume_mute, volume_unmute,
volume_status,
brightness_set, brightness_increase, brightness_decrease, brightness_status,
enable_wifi, disable_wifi, wifi_status,
enable_bluetooth, disable_bluetooth, bluetooth_status,
web_search,
list_files, search_files, create_file, create_directory, rename_file,
move_file, delete_file,
clarification, conversation, unsupported

EXAMPLES

"search for cats"            -> {"intent":"web_search","target":"cats","response":""}
"can you google the weather" -> {"intent":"web_search","target":"weather","response":""}
"look up python decorators"  -> {"intent":"web_search","target":"python decorators","response":""}
"what is the news today"     -> {"intent":"web_search","target":"news today","response":""}
"open spotify"               -> {"intent":"open_application","target":"spotify","response":""}
"make it louder"             -> {"intent":"volume_increase","target":"10","response":""}
"how are you"                -> {"intent":"conversation","target":"","response":"I am running well. What would you like to do?"}
"what can you do"            -> {"intent":"conversation","target":"","response":"I can open and close apps, control volume, brightness, Wi-Fi and Bluetooth, search the web and manage files."}

Return ONLY valid JSON:
{
    "intent": "allowed_intent",
    "target": "value",
    "response": "natural reply when intent is conversation, otherwise empty"
}
"""


# =========================================================
# WARM UP
# =========================================================

def warm_up():
    """Load the classifier now so the first real command is not slow.

    Mirrors the Kokoro warm-up. Failure is not fatal: the brain simply loads
    on first use, exactly as it did before.
    """

    try:

        requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": "ok",
                    }
                ],
                "stream": False,
                "keep_alive": KEEP_ALIVE,
                "options": {
                    "num_predict": 1,
                },
            },
            timeout=180,
        ).raise_for_status()

        return True


    except Exception as error:

        print(
            "[BRAIN] Warm-up unavailable:",
            error,
        )

        return False


# =========================================================
# CLEAN TEXT
# =========================================================

def _clean(text):

    return re.sub(
        r"\s+",
        " ",
        str(text).strip().lower()
    )


# =========================================================
# EXTRACT PERCENTAGE
# =========================================================

def _extract_percentage(text):

    match = re.search(
        r"\b(\d{1,3})\s*(?:%|percent|percentage)\b",
        text,
        re.IGNORECASE
    )


    if match:

        value = int(
            match.group(1)
        )

        return max(
            0,
            min(
                100,
                value
            )
        )


    match = re.search(
        r"\b(?:volume|brightness)\s+(?:to\s+)?(\d{1,3})\b",
        text,
        re.IGNORECASE
    )


    if match:

        value = int(
            match.group(1)
        )

        return max(
            0,
            min(
                100,
                value
            )
        )


    return None


# =========================================================
# WEB SEARCH INTENT
# =========================================================
#
# Searching is the single most common thing a user asks for, and the 3.8B
# classifier answers "conversation" to every phrasing of it. These rules run
# before the model so a search is never talked about instead of performed.
#
# =========================================================

# Politeness and filler that can precede any request.
_LEAD = r"(?:please\s+|can\s+you\s+|could\s+you\s+|would\s+you\s+|wrecz[,\s]+)*"

# Filler between the verb and the actual query.
_FOR = r"(?:for\s+|about\s+|up\s+|me\s+|some\s+|the\s+latest\s+)*"

_ENGINES = r"(?:google|bing|duckduckgo|the\s+web|the\s+internet|online|the\s+net)"

# A search verb that means "the filesystem", not "the web".
_FILE_HINTS = (
    "file",
    "files",
    "folder",
    "folders",
    "directory",
    "document",
    "documents",
    "on my pc",
    "on my computer",
    "on this pc",
    "my drive",
    "my disk",
)

# Questions that need live information rather than the model's own memory.
_REALTIME_HINTS = (
    "weather",
    "forecast",
    "temperature outside",
    "news",
    "headlines",
    "stock price",
    "share price",
    "exchange rate",
    "who won",
    "score of",
    "match score",
)

_SEARCH_PATTERNS = (
    # "open chrome and search for cats", and the same without the "and":
    # "open chrome search for cats". The browser opens either way, so honour
    # the search rather than trying to launch "chrome search for cats".
    # The app name is non-greedy and uncaptured so multi-word names work
    # ("open visual studio code and search for x") without polluting the query.
    rf"^{_LEAD}(?:open|launch|start|run|go\s+to)\s+.+?\s+"
    rf"(?:and\s+|then\s+|and\s+then\s+)?"
    rf"(?:search|google|look\s*up|browse)\s+{_FOR}(.+)$",

    # "do/run/start a google search for cats", "start searching for cats"
    rf"^{_LEAD}(?:do|run|start|perform|make)\s+(?:a\s+|an\s+)?"
    rf"(?:google\s+|web\s+|quick\s+)?search(?:ing)?\s+{_FOR}(.+)$",

    # "search google for cats", "look online for cats", "search the web cats"
    rf"^{_LEAD}(?:search|look|browse)\s+(?:on\s+|in\s+|through\s+)?"
    rf"{_ENGINES}\s+{_FOR}(.+)$",

    # "google cats", "bing cats"
    rf"^{_LEAD}(?:google|bing|duckduckgo)\s+{_FOR}(.+)$",

    # "search youtube for lofi" -> "youtube lofi"
    rf"^{_LEAD}(?:search|browse)\s+(?!for\b|about\b)(\S+)\s+for\s+(.+)$",

    # The plain forms: "search for cats", "search cats", "look up cats"
    rf"^{_LEAD}(?:search|look\s*up|lookup|browse)\s+{_FOR}(.+)$",

    # "find me some lofi playlists", "find information about cats"
    rf"^{_LEAD}find\s+(?:me\s+)?(?:some\s+|information\s+about\s+|info\s+about\s+|"
    rf"info\s+on\s+)(.+)$",

    # "what is the weather in delhi" - handled via _REALTIME_HINTS below.
)

# A sentence that starts by commanding the machine is not an information
# request, whatever nouns it happens to contain.
_IMPERATIVE = re.compile(
    r"^(?:open|launch|start|run|close|exit|quit|shut|turn|set|enable|"
    r"disable|mute|unmute|play|stop|pause|increase|decrease|delete|"
    r"remove|rename|move|create)\b",
    re.IGNORECASE,
)

# Trailing filler that should not end up in the query.
_TRAILING = re.compile(
    r"\s+(?:please|for\s+me|right\s+now|quickly)\s*$",
    re.IGNORECASE,
)


def _clean_query(value):
    """Tidy a captured query so the browser gets what the user meant."""

    query = re.sub(r"\s+", " ", str(value or "").strip())
    query = _TRAILING.sub("", query)
    query = query.strip(" ?.!,")

    # Strip a filler word the capture group may have swallowed.
    query = re.sub(
        r"^(?:for|about|up|me|some|of)\s+",
        "",
        query,
        flags=re.IGNORECASE,
    )

    return query.strip()


def _web_search_intent(user_input):
    """Detect a request to search the web, and extract the query."""

    text = _clean(user_input)

    if not text:
        return None

    # A search for files is a different skill. Let it fall through.
    if any(hint in text for hint in _FILE_HINTS):
        return None

    for pattern in _SEARCH_PATTERNS:

        match = re.match(pattern, text, re.IGNORECASE)

        if not match:
            continue

        # The "search <site> for <query>" form captures two groups.
        groups = [g for g in match.groups() if g]
        query = _clean_query(" ".join(groups))

        if query:

            return {
                "intent": "web_search",
                "target": query,
            }

    # Live information the model cannot know, phrased as a question.
    #
    # Only when the sentence is not already a command: "turn off the news app"
    # and "close weather" mention these words but are not searches.
    if (
        not _IMPERATIVE.match(text)
        and
        any(hint in text for hint in _REALTIME_HINTS)
    ):

        query = _clean_query(
            re.sub(
                rf"^{_LEAD}(?:what(?:'s| is| are)?|hows?|tell\s+me)\s+"
                r"(?:the\s+)?",
                "",
                text,
                flags=re.IGNORECASE,
            )
        )

        if query:

            return {
                "intent": "web_search",
                "target": query,
            }

    return None


# =========================================================
# LOCAL SYSTEM INTENT
# =========================================================
#
# These rules run BEFORE Phi.
#
# This is intentional.
#
# Critical local controls such as Wi-Fi and Bluetooth
# must never accidentally become web searches.
#
# =========================================================

def _local_intent(user_input):

    text = _clean(
        user_input
    )


    # =====================================================
    # WIFI
    # =====================================================

    if (
        "wifi" in text
        or
        "wi-fi" in text
        or
        "wireless" in text
    ):

        if any(
            phrase in text
            for phrase in (
                "turn on",
                "switch on",
                "enable",
                "activate",
                "turn back on",
                "switch back on",
                "start"
            )
        ):

            return {
                "intent": "enable_wifi",
                "target": ""
            }


        if any(
            phrase in text
            for phrase in (
                "turn off",
                "switch off",
                "disable",
                "deactivate",
                "stop"
            )
        ):

            return {
                "intent": "disable_wifi",
                "target": ""
            }


        if any(
            phrase in text
            for phrase in (
                "status",
                "check",
                "is wifi on",
                "is wi-fi on",
                "is it enabled",
                "what is the wifi"
            )
        ):

            return {
                "intent": "wifi_status",
                "target": ""
            }


    # =====================================================
    # BLUETOOTH
    # =====================================================

    if "bluetooth" in text:

        if any(
            phrase in text
            for phrase in (
                "turn on",
                "switch on",
                "enable",
                "activate",
                "turn back on",
                "switch back on"
            )
        ):

            return {
                "intent": "enable_bluetooth",
                "target": ""
            }


        if any(
            phrase in text
            for phrase in (
                "turn off",
                "switch off",
                "disable",
                "deactivate"
            )
        ):

            return {
                "intent": "disable_bluetooth",
                "target": ""
            }


        if any(
            phrase in text
            for phrase in (
                "status",
                "check",
                "is bluetooth on",
                "is it enabled",
                "what is the bluetooth"
            )
        ):

            return {
                "intent": "bluetooth_status",
                "target": ""
            }


    # =====================================================
    # VOLUME
    # =====================================================

    if any(
        word in text
        for word in (
            "volume",
            "sound",
            "audio",
            "louder",
            "quieter",
            "quiet",
            "mute",
            "unmute",
            "silence"
        )
    ):

        percentage = (
            _extract_percentage(
                text
            )
        )


        if percentage is not None:

            return {
                "intent": "volume_set",
                "target": str(
                    percentage
                )
            }


        if any(
            phrase in text
            for phrase in (
                "unmute",
                "remove mute",
                "turn off mute",
                "sound back on",
                "restore sound"
            )
        ):

            return {
                "intent": "volume_unmute",
                "target": ""
            }


        if (
            "mute" in text
            or
            "silence" in text
        ):

            return {
                "intent": "volume_mute",
                "target": ""
            }


        if any(
            phrase in text
            for phrase in (
                "increase",
                "turn up",
                "louder",
                "raise",
                "higher",
                "too quiet",
                "too low"
            )
        ):

            return {
                "intent": "volume_increase",
                "target": "10"
            }


        if any(
            phrase in text
            for phrase in (
                "decrease",
                "turn down",
                "lower",
                "quieter",
                "too loud",
                "too high"
            )
        ):

            return {
                "intent": "volume_decrease",
                "target": "10"
            }


        if any(
            phrase in text
            for phrase in (
                "check volume",
                "volume status",
                "what is the volume",
                "how loud"
            )
        ):

            return {
                "intent": "volume_status",
                "target": ""
            }


    # =====================================================
    # BRIGHTNESS
    # =====================================================

    if any(
        phrase in text
        for phrase in (
            "brightness",
            "screen brightness",
            "display brightness",
            "screen is too dark",
            "screen is too bright",
            "brighter",
            "brighten",
            "darker",
            "darken",
            "dimmer",
            "dim the screen"
        )
    ):

        percentage = (
            _extract_percentage(
                text
            )
        )


        if percentage is not None:

            return {
                "intent": "brightness_set",
                "target": str(
                    percentage
                )
            }


        if any(
            phrase in text
            for phrase in (
                "increase",
                "brighter",
                "brighten",
                "turn up",
                "too dark"
            )
        ):

            return {
                "intent": "brightness_increase",
                "target": "10"
            }


        if any(
            phrase in text
            for phrase in (
                "decrease",
                "darker",
                "darken",
                "dim",
                "turn down",
                "too bright",
                "lower"
            )
        ):

            return {
                "intent": "brightness_decrease",
                "target": "10"
            }


        if any(
            phrase in text
            for phrase in (
                "status",
                "check",
                "what is"
            )
        ):

            return {
                "intent": "brightness_status",
                "target": ""
            }


    # =====================================================
    # WEB SEARCH
    # =====================================================

    web = _web_search_intent(text)

    if web is not None:

        return web


    return None


# =========================================================
# APPLICATION INTENT
# =========================================================

# Words that mean the user is describing an activity, not naming a program.
# Without this "start searching for cats" tries to launch an app called
# "searching for cats".
_NOT_AN_APP = re.compile(
    r"^(?:a|an|the)?\s*"
    r"(?:search|searching|google|browsing|browse|web|internet|"
    r"look\s*up|lookup)\b",
    re.IGNORECASE,
)

# A rule should only claim a request when it is sure. Anything below is a
# sign the phrase is a sentence rather than a program name, so it is handed
# to the model instead of being forced into an app launch.

# Joining words mean a compound request ("open chrome and play music") or an
# activity ("open a file to edit"). Real application names do not contain them.
_APP_JOINERS = re.compile(
    r"\b(?:and|then|or|to|for|about|with|from|into|so)\b",
    re.IGNORECASE,
)

# "start a conversation", "run a marathon". Programs are not called "a X".
_APP_INDEFINITE = re.compile(r"^(?:a|an)\s+", re.IGNORECASE)

# Longest plausible application name, e.g. "microsoft visual studio code".
_MAX_APP_WORDS = 4


def _looks_like_application(target):
    """True only when the phrase is confidently a program name."""

    if not target:
        return False

    if _NOT_AN_APP.match(target):
        return False

    if _APP_INDEFINITE.match(target):
        return False

    if _APP_JOINERS.search(target):
        return False

    return len(target.split()) <= _MAX_APP_WORDS


def _application_intent(user_input):

    text = _clean(
        user_input
    )


    match = re.match(
        r"^(?:please\s+)?"
        r"(?:open|launch|start|run)\s+"
        r"(.+?)$",
        text
    )


    if match:

        target = (
            match.group(1)
            .strip()
        )


        if _looks_like_application(target):

            return {
                "intent":
                    "open_application",

                "target":
                    target
            }


    match = re.match(
        r"^(?:please\s+)?"
        r"(?:close|exit|quit|shut)\s+"
        r"(.+?)$",
        text
    )


    if match:

        target = (
            match.group(1)
            .strip()
        )


        if _looks_like_application(target):

            return {
                "intent":
                    "close_application",

                "target":
                    target
            }


    return None


# =========================================================
# PHI CLASSIFIER
# =========================================================

def _classify_with_llm(user_input):
    """
    Classify the current request while giving the model a small amount of
    conversational context. The output remains machine-readable JSON.
    """

    context = STATE.llm_context()

    contextual_user_message = (
        "Previous conversation context:\n"
        f"{context}\n\n"
        "Current user request:\n"
        f"{user_input}"
    )

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": CLASSIFIER_PROMPT,
            },
            {
                "role": "user",
                "content": contextual_user_message,
            },
        ],
        "format": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": [
                        "open_application",
                        "close_application",
                        "volume_set",
                        "volume_increase",
                        "volume_decrease",
                        "volume_mute",
                        "volume_unmute",
                        "volume_status",
                        "brightness_set",
                        "brightness_increase",
                        "brightness_decrease",
                        "brightness_status",
                        "enable_wifi",
                        "disable_wifi",
                        "wifi_status",
                        "enable_bluetooth",
                        "disable_bluetooth",
                        "bluetooth_status",
                        "web_search",
                        "list_files",
                        "search_files",
                        "create_file",
                        "create_directory",
                        "rename_file",
                        "move_file",
                        "delete_file",
                        "clarification",
                        "conversation",
                        "unsupported",
                    ],
                },
                "target": {
                    "type": "string",
                },
                "response": {
                    "type": "string",
                },
            },
            "required": [
                "intent",
                "target",
                "response",
            ],
        },
        "options": {
            "temperature": 0.1,
        },
        "stream": False,
        "keep_alive": KEEP_ALIVE,
    }

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=60,
    )

    response.raise_for_status()

    data = response.json()

    content = data["message"]["content"].strip()

    content = re.sub(
        r"^```json\s*",
        "",
        content,
        flags=re.IGNORECASE,
    )
    content = re.sub(
        r"^```\s*",
        "",
        content,
    )
    content = re.sub(
        r"\s*```$",
        "",
        content,
    )

    return json.loads(content.strip())


# =========================================================
# INTENT → WRECZ COMMAND
# =========================================================

def _build_command(
    intent,
    target=""
):

    intent = str(
        intent
    ).strip().lower()


    target = str(
        target or ""
    ).strip()


    # =====================================================
    # APPLICATIONS
    # =====================================================

    if intent == "open_application":

        return {
            "intent": intent,
            "action": "open_app",
            "target": target,
            "internet": "NO",
            "confirmation": "NO",
            "reason": "The user wants to open an application."
        }


    if intent == "close_application":

        return {
            "intent": intent,
            "action": "close_app",
            "target": target,
            "internet": "NO",
            "confirmation": "YES",
            "reason": "The user wants to close an application."
        }


    # =====================================================
    # WIFI
    # =====================================================

    if intent == "enable_wifi":

        return {
            "intent": intent,
            "action": "wifi_control",
            "target": "on",
            "internet": "NO",
            "confirmation": "NO",
            "reason": "The user wants Wi-Fi enabled."
        }


    if intent == "disable_wifi":

        return {
            "intent": intent,
            "action": "wifi_control",
            "target": "off",
            "internet": "NO",
            "confirmation": "NO",
            "reason": "The user wants Wi-Fi disabled."
        }


    if intent == "wifi_status":

        return {
            "intent": intent,
            "action": "wifi_control",
            "target": "status",
            "internet": "NO",
            "confirmation": "NO",
            "reason": "The user wants Wi-Fi status."
        }


    # =====================================================
    # BLUETOOTH
    # =====================================================

    if intent == "enable_bluetooth":

        return {
            "intent": intent,
            "action": "bluetooth_control",
            "target": "on",
            "internet": "NO",
            "confirmation": "NO",
            "reason": "The user wants Bluetooth enabled."
        }


    if intent == "disable_bluetooth":

        return {
            "intent": intent,
            "action": "bluetooth_control",
            "target": "off",
            "internet": "NO",
            "confirmation": "NO",
            "reason": "The user wants Bluetooth disabled."
        }


    if intent == "bluetooth_status":

        return {
            "intent": intent,
            "action": "bluetooth_control",
            "target": "status",
            "internet": "NO",
            "confirmation": "NO",
            "reason": "The user wants Bluetooth status."
        }


    # =====================================================
    # VOLUME
    # =====================================================

    if intent == "volume_set":

        return {
            "intent": intent,
            "action": "volume_control",
            "target": f"set|{target}",
            "internet": "NO",
            "confirmation": "NO",
            "reason": "The user wants to set system volume."
        }


    if intent == "volume_increase":

        return {
            "intent": intent,
            "action": "volume_control",
            "target": f"increase|{target or '10'}",
            "internet": "NO",
            "confirmation": "NO",
            "reason": "The user wants louder audio."
        }


    if intent == "volume_decrease":

        return {
            "intent": intent,
            "action": "volume_control",
            "target": f"decrease|{target or '10'}",
            "internet": "NO",
            "confirmation": "NO",
            "reason": "The user wants quieter audio."
        }


    if intent == "volume_mute":

        return {
            "intent": intent,
            "action": "volume_control",
            "target": "mute",
            "internet": "NO",
            "confirmation": "NO",
            "reason": "The user wants audio muted."
        }


    if intent == "volume_unmute":

        return {
            "intent": intent,
            "action": "volume_control",
            "target": "unmute",
            "internet": "NO",
            "confirmation": "NO",
            "reason": "The user wants audio unmuted."
        }


    if intent == "volume_status":

        return {
            "intent": intent,
            "action": "volume_control",
            "target": "get",
            "internet": "NO",
            "confirmation": "NO",
            "reason": "The user wants volume status."
        }


    # =====================================================
    # BRIGHTNESS
    # =====================================================

    if intent == "brightness_set":

        return {
            "intent": intent,
            "action": "brightness_control",
            "target": f"set|{target}",
            "internet": "NO",
            "confirmation": "NO",
            "reason": "The user wants to set brightness."
        }


    if intent == "brightness_increase":

        return {
            "intent": intent,
            "action": "brightness_control",
            "target": f"increase|{target or '10'}",
            "internet": "NO",
            "confirmation": "NO",
            "reason": "The user wants increased brightness."
        }


    if intent == "brightness_decrease":

        return {
            "intent": intent,
            "action": "brightness_control",
            "target": f"decrease|{target or '10'}",
            "internet": "NO",
            "confirmation": "NO",
            "reason": "The user wants decreased brightness."
        }


    if intent == "brightness_status":

        return {
            "intent": intent,
            "action": "brightness_control",
            "target": "get",
            "internet": "NO",
            "confirmation": "NO",
            "reason": "The user wants brightness status."
        }


    # =====================================================
    # WEB SEARCH
    # =====================================================

    if intent == "web_search":

        if not target:

            return {
                "intent": "clarification",
                "action": "clarification",
                "target": "",
                "internet": "NO",
                "confirmation": "NO",
                "reason": "The search query is missing."
            }


        return {
            "intent": intent,
            "action": "web_search",
            "target": target,
            "internet": "REQUEST",
            "confirmation": "NO",
            "reason": "The user explicitly requested a web search."
        }


    # =====================================================
    # FILES
    # =====================================================

    if intent == "list_files":

        return {
            "intent": intent,
            "action": "list_files",
            "target": target or ".",
            "internet": "NO",
            "confirmation": "NO",
            "reason": "The user wants to list files."
        }


    if intent == "search_files":

        return {
            "intent": intent,
            "action": "search_files",
            "target": target,
            "internet": "NO",
            "confirmation": "NO",
            "reason": "The user wants to search local files."
        }


    if intent == "create_file":

        return {
            "intent": intent,
            "action": "create_file",
            "target": target,
            "internet": "NO",
            "confirmation": "YES",
            "reason": "The user wants to create a file."
        }


    if intent == "create_directory":

        return {
            "intent": intent,
            "action": "create_directory",
            "target": target,
            "internet": "NO",
            "confirmation": "YES",
            "reason": "The user wants to create a directory."
        }


    if intent == "rename_file":

        return {
            "intent": intent,
            "action": "rename_file",
            "target": target,
            "internet": "NO",
            "confirmation": "YES",
            "reason": "The user wants to rename a file."
        }


    if intent == "move_file":

        return {
            "intent": intent,
            "action": "move_file",
            "target": target,
            "internet": "NO",
            "confirmation": "YES",
            "reason": "The user wants to move a file."
        }


    if intent == "delete_file":

        return {
            "intent": intent,
            "action": "delete_file",
            "target": target,
            "internet": "NO",
            "confirmation": "YES",
            "reason": "The user wants to delete a file."
        }


    # =====================================================
    # CLARIFICATION
    # =====================================================

    if intent == "clarification":

        return {
            "intent": intent,
            "action": "clarification",
            "target": "",
            "internet": "NO",
            "confirmation": "NO",
            "reason": "The request requires clarification."
        }


    # =====================================================
    # UNSUPPORTED
    # =====================================================

    return {
        "intent": "unsupported",
        "action": "unsupported",
        "target": target,
        "internet": "NO",
        "confirmation": "NO",
        "reason": "The requested capability is unavailable."
    }


# =========================================================
# FINAL VALIDATION
# =========================================================

def validate_command(command):

    allowed_actions = {

        "open_app",
        "close_app",

        "volume_control",
        "brightness_control",

        "wifi_control",
        "bluetooth_control",

        "web_search",

        "list_files",
        "search_files",
        "create_file",
        "create_directory",
        "rename_file",
        "move_file",
        "delete_file",

        "clarification",
        "conversation",
        "unsupported"
    }


    action = command.get(
        "action",
        "unsupported"
    )


    if action not in allowed_actions:

        return _build_command(
            "unsupported"
        )


    # -----------------------------------------------------
    # LOCAL ACTIONS NEVER USE INTERNET
    # -----------------------------------------------------

    local_actions = {

        "open_app",
        "close_app",

        "volume_control",
        "brightness_control",

        "wifi_control",
        "bluetooth_control",

        "list_files",
        "search_files",
        "create_file",
        "create_directory",
        "rename_file",
        "move_file",
        "delete_file"
    }


    if action in local_actions:

        command[
            "internet"
        ] = "NO"


    # -----------------------------------------------------
    # WEB SEARCH ALWAYS USES SECURITY GATE
    # -----------------------------------------------------

    if action == "web_search":

        command[
            "internet"
        ] = "REQUEST"

        command[
            "confirmation"
        ] = "NO"


        if not str(
            command.get(
                "target",
                ""
            )
        ).strip():

            return _build_command(
                "clarification"
            )


    # -----------------------------------------------------
    # SYSTEM CONTROLS
    # -----------------------------------------------------

    if action in {

        "open_app",

        "volume_control",

        "brightness_control",

        "wifi_control",

        "bluetooth_control"

    }:

        command[
            "confirmation"
        ] = "NO"


    # -----------------------------------------------------
    # CLOSE APPLICATION
    # -----------------------------------------------------

    if action == "close_app":

        command[
            "confirmation"
        ] = "YES"


    # -----------------------------------------------------
    # FILES
    # -----------------------------------------------------

    if action in {
        "list_files",
        "search_files"
    }:

        command[
            "confirmation"
        ] = "NO"


    if action in {
        "create_file",
        "create_directory",
        "rename_file",
        "move_file",
        "delete_file"
    }:

        command[
            "confirmation"
        ] = "YES"


    # -----------------------------------------------------
    # CLARIFICATION / UNSUPPORTED
    # -----------------------------------------------------

    if action in {
        "clarification",
        "unsupported"
    }:

        command[
            "internet"
        ] = "NO"

        command[
            "confirmation"
        ] = "NO"


    return command


# =========================================================
# MAIN BRAIN
# =========================================================

def ask_wrecz(user_input):
    if not user_input:
        command = _build_command("clarification")
        STATE.record(user_input, command)
        return command

    original_text = str(user_input).strip()

    # Resolve short conversational references before the fast local parser.
    text = _clean(STATE.resolve(original_text))

    # 1. Fast deterministic local controls
    local_result = _local_intent(text)
    if local_result is not None:
        command = validate_command(
            _build_command(
                local_result["intent"],
                local_result["target"],
            )
        )
        STATE.record(original_text, command)
        return command

    # 2. Fast deterministic application controls
    application_result = _application_intent(text)
    if application_result is not None:
        command = validate_command(
            _build_command(
                application_result["intent"],
                application_result["target"],
            )
        )
        STATE.record(original_text, command)
        return command

    # 3. Conversational LLM classification
    try:
        result = _classify_with_llm(text)

        # Normal conversation stays outside the action/router pipeline.
        # Phi supplies the natural response; main.py sends it to voice directly.
        if str(result.get("intent", "")).strip().lower() == "conversation":
            response = str(result.get("response", "") or "").strip()

            if not response:
                response = (
                    "I'm here and ready to help. "
                    "What would you like to talk about?"
                )

            conversation = {
                "intent": "conversation",
                "action": "conversation",
                "target": "",
                "response": response,
                "internet": "NO",
                "confirmation": "NO",
                "reason": "The user is having a normal conversation.",
            }

            STATE.record(original_text, conversation)
            return conversation

        command = validate_command(
            _build_command(
                result.get("intent", "unsupported"),
                result.get("target", ""),
            )
        )

        STATE.record(original_text, command)
        return command

    except requests.exceptions.ConnectionError:
        return {
            "intent": "error",
            "action": "unsupported",
            "target": "",
            "internet": "NO",
            "confirmation": "NO",
            "reason": "Wrecz cannot connect to Ollama.",
        }

    except requests.exceptions.Timeout:
        return {
            "intent": "error",
            "action": "unsupported",
            "target": "",
            "internet": "NO",
            "confirmation": "NO",
            "reason": "Wrecz brain timed out.",
        }

    except json.JSONDecodeError:
        return {
            "intent": "error",
            "action": "unsupported",
            "target": "",
            "internet": "NO",
            "confirmation": "NO",
            "reason": "Wrecz brain returned invalid JSON.",
        }

    except Exception as error:
        return {
            "intent": "error",
            "action": "unsupported",
            "target": "",
            "internet": "NO",
            "confirmation": "NO",
            "reason": f"Brain error: {error}",
        }