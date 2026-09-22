"""Runtime settings shared by the CLI and the frontend bridge.

These back the toggles in the frontend Settings panel.

confirm_destructive keeps WRECZ's original behaviour. ask_before_web does not:
searching used to interrupt with a permission prompt, which made the single
most common request feel broken. Turning the toggle on restores the prompt.

ask_before_web       False - web actions are carried out without prompting.
                             The session still starts offline; the first web
                             action turns internet on and is logged. When
                             True, every web action asks first.
confirm_destructive  True  - close_app and write/delete filesystem actions ask
                             for confirmation (existing behaviour).
"""

import threading


class RuntimeSettings:

    def __init__(self):

        self._lock = threading.Lock()

        self._values = {
            "ask_before_web": False,
            "confirm_destructive": True,
        }


    # =========================================================
    # READ
    # =========================================================

    @property
    def ask_before_web(self):

        with self._lock:

            return self._values["ask_before_web"]


    @property
    def confirm_destructive(self):

        with self._lock:

            return self._values["confirm_destructive"]


    def as_dict(self):

        with self._lock:

            return dict(self._values)


    # =========================================================
    # WRITE
    # =========================================================

    def update(self, **changes):
        """Apply known settings and return the full resulting state.

        Unknown keys are ignored so a newer frontend cannot inject arbitrary
        values into the security path.
        """

        with self._lock:

            for key, value in changes.items():

                if key in self._values and value is not None:

                    self._values[key] = bool(value)

            return dict(self._values)


SETTINGS = RuntimeSettings()
