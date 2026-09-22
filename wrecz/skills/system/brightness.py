import subprocess


# =========================================================
# GET BRIGHTNESS
# =========================================================

def get_brightness():

    try:

        command = [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",

            (
                "Get-CimInstance "
                "-Namespace root/WMI "
                "-ClassName WmiMonitorBrightness "
                "| Where-Object {$_.Active -eq $true} "
                "| Select-Object -First 1 "
                "-ExpandProperty CurrentBrightness"
            )
        ]


        result = subprocess.run(

            command,

            capture_output=True,

            text=True,

            timeout=10
        )


        if result.returncode != 0:

            return (
                False,
                "Windows could not read brightness."
            )


        output = result.stdout.strip()


        if not output:

            return (
                False,
                "Windows did not return brightness."
            )


        brightness = int(output)


        brightness = max(
            0,
            min(
                100,
                brightness
            )
        )


        return (
            True,
            brightness
        )


    except Exception as error:

        return (
            False,
            f"Could not read brightness: {error}"
        )


# =========================================================
# SET BRIGHTNESS
# =========================================================

def set_brightness(
    percentage
):

    try:

        percentage = int(
            round(
                float(percentage)
            )
        )


    except (
        TypeError,
        ValueError
    ):

        return (
            False,
            "Brightness must be between 0 and 100."
        )


    percentage = max(
        0,
        min(
            100,
            percentage
        )
    )


    # =====================================================
    # USE INVOKE-CIMMETHOD
    # =====================================================

    powershell_script = (
        "$monitor="
        "Get-CimInstance "
        "-Namespace root/WMI "
        "-ClassName WmiMonitorBrightnessMethods "
        "| Where-Object {$_.Active -eq $true} "
        "| Select-Object -First 1;"
        "if ($null -eq $monitor) { exit 2 };"
        "$result="
        "Invoke-CimMethod "
        "-InputObject $monitor "
        "-MethodName WmiSetBrightness "
        f"-Arguments @{{Timeout=0;Brightness={percentage}}};"
        "if ($result.ReturnValue -ne 0) { "
        "exit $result.ReturnValue "
        "}"
    )


    try:

        result = subprocess.run(

            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                powershell_script
            ],

            capture_output=True,

            text=True,

            timeout=10
        )


        if result.returncode == 2:

            return (
                False,
                "No active brightness-capable display was found."
            )


        if result.returncode != 0:

            return (
                False,
                (
                    "Windows rejected the brightness change. "
                    f"Return code: {result.returncode}"
                )
            )


        return (
            True,
            f"Brightness set to {percentage}%."
        )


    except subprocess.TimeoutExpired:

        return (
            False,
            "Brightness change timed out."
        )


    except Exception as error:

        return (
            False,
            f"Could not set brightness: {error}"
        )


# =========================================================
# INCREASE BRIGHTNESS
# =========================================================

def increase_brightness(
    amount=10
):

    try:

        amount = float(
            amount
        )

    except (
        TypeError,
        ValueError
    ):

        amount = 10


    success, current = (
        get_brightness()
    )


    if not success:

        return (
            False,
            current
        )


    target = (
        current + amount
    )


    return set_brightness(
        target
    )


# =========================================================
# DECREASE BRIGHTNESS
# =========================================================

def decrease_brightness(
    amount=10
):

    try:

        amount = float(
            amount
        )

    except (
        TypeError,
        ValueError
    ):

        amount = 10


    success, current = (
        get_brightness()
    )


    if not success:

        return (
            False,
            current
        )


    target = (
        current - amount
    )


    return set_brightness(
        target
    )