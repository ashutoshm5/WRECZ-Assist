import threading

import pystray

from PIL import Image, ImageDraw


class SecurityTray:

    def __init__(self, security):

        self.security = security
        self.icon = None


    # =========================================================
    # CREATE ICON
    # =========================================================

    def create_image(self):

        image = Image.new(
            "RGB",
            (64, 64),
            "black"
        )

        draw = ImageDraw.Draw(image)

        if self.security.is_internet_enabled():

            # Green indicator
            draw.ellipse(
                (12, 12, 52, 52),
                fill="green"
            )

        else:

            # Red indicator
            draw.ellipse(
                (12, 12, 52, 52),
                fill="red"
            )

        return image


    # =========================================================
    # STATUS TEXT
    # =========================================================

    def status_text(self):

        if self.security.is_internet_enabled():

            return "Internet: ON"

        return "Internet: OFF"


    # =========================================================
    # TOGGLE
    # =========================================================

    def toggle(self, icon, item):

        self.security.toggle_internet()

        self.refresh()


    # =========================================================
    # FORCE OFF
    # =========================================================

    def disable(self, icon, item):

        self.security.force_off()

        self.refresh()


    # =========================================================
    # REFRESH
    # =========================================================

    def refresh(self):

        if self.icon is None:

            return

        self.icon.icon = self.create_image()

        self.icon.title = (
            f"Wrecz Security | "
            f"{self.status_text()}"
        )


    # =========================================================
    # RUN
    # =========================================================

    def run(self):

        menu = pystray.Menu(

            pystray.MenuItem(
                lambda item: self.status_text(),
                None,
                enabled=False
            ),

            pystray.Menu.SEPARATOR,

            pystray.MenuItem(
                "Toggle Internet",
                self.toggle
            ),

            pystray.MenuItem(
                "Emergency OFF",
                self.disable
            )
        )


        self.icon = pystray.Icon(

            "WreczSecurity",

            self.create_image(),

            "Wrecz Security | Internet: OFF",

            menu
        )


        self.icon.run()


    # =========================================================
    # START BACKGROUND
    # =========================================================

    def start(self):

        thread = threading.Thread(
            target=self.run,
            daemon=True
        )

        thread.start()

        return thread