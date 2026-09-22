import asyncio

from winrt.windows.devices.radios import (
    Radio,
    RadioState
)


# =========================================================
# WRECZ WI-FI RADIO CONTROL
# =========================================================

# Windows.Devices.Radios values
#
# RadioKind:
#     WiFi = 1
#
# RadioState:
#     On  = 1
#     Off = 2
#
# RadioAccessStatus:
#     Allowed = 1
# =========================================================


WIFI_KIND = 1

RADIO_ON = RadioState(1)

RADIO_OFF = RadioState(2)

ACCESS_ALLOWED = 1


# =========================================================
# FIND WI-FI RADIO
# =========================================================

async def _find_wifi_radio():

    radios = await Radio.get_radios_async()


    for radio in radios:

        try:

            kind_value = int(
                radio.kind
            )

        except Exception:

            continue


        if kind_value == WIFI_KIND:

            return radio


    return None


# =========================================================
# GET WI-FI STATUS
# =========================================================

def get_wifi_status():

    async def _get():

        radio = await _find_wifi_radio()


        if radio is None:

            return (
                False,
                "Windows could not find a Wi-Fi radio."
            )


        state_value = int(
            radio.state
        )


        if state_value == 1:

            state = "ON"

            enabled = True


        elif state_value == 2:

            state = "OFF"

            enabled = False


        elif state_value == 3:

            state = "DISABLED"

            enabled = False


        else:

            state = "UNKNOWN"

            enabled = False


        return (

            True,

            {
                "name": radio.name,

                "state": state,

                "enabled": enabled
            }
        )


    try:

        return asyncio.run(
            _get()
        )


    except Exception as error:

        return (

            False,

            f"Could not read Wi-Fi radio: {error}"
        )


# =========================================================
# SET WI-FI STATE
# =========================================================

def _set_wifi_state(
    desired_state
):

    async def _set():

        radio = await _find_wifi_radio()


        if radio is None:

            return (

                False,

                "Windows could not find a Wi-Fi radio."
            )


        current_state = int(
            radio.state
        )


        desired_value = int(
            desired_state
        )


        # -------------------------------------------------
        # Already in requested state
        # -------------------------------------------------

        if current_state == desired_value:

            if desired_value == 1:

                return (

                    True,

                    "Wi-Fi is already on."
                )


            return (

                True,

                "Wi-Fi is already off."
            )


        # -------------------------------------------------
        # Request permission
        # -------------------------------------------------

        access = (
            await Radio.request_access_async()
        )


        access_value = int(
            access
        )


        if access_value != ACCESS_ALLOWED:

            return (

                False,

                (
                    "Windows denied Wrecz permission "
                    "to control the Wi-Fi radio. "
                    f"Access status: {access}"
                )
            )


        # -------------------------------------------------
        # Change state
        # -------------------------------------------------

        result = (
            await radio.set_state_async(
                desired_state
            )
        )


        result_value = int(
            result
        )


        if result_value != ACCESS_ALLOWED:

            return (

                False,

                (
                    "Windows did not allow the "
                    "Wi-Fi state change. "
                    f"Result: {result}"
                )
            )


        # -------------------------------------------------
        # Windows applies the radio change asynchronously.
        # -------------------------------------------------

        await asyncio.sleep(
            1.0
        )


        # -------------------------------------------------
        # Verify final state
        # -------------------------------------------------

        updated_radio = (
            await _find_wifi_radio()
        )


        if updated_radio is None:

            return (

                False,

                "Wi-Fi radio disappeared after the change."
            )


        final_state = int(
            updated_radio.state
        )


        if final_state != desired_value:

            return (

                False,

                (
                    "Windows accepted the Wi-Fi request, "
                    "but the radio did not reach the "
                    "requested state."
                )
            )


        if desired_value == 1:

            return (

                True,

                "Wi-Fi turned on."
            )


        return (

            True,

            "Wi-Fi turned off."
        )


    try:

        return asyncio.run(
            _set()
        )


    except Exception as error:

        return (

            False,

            f"Could not change Wi-Fi state: {error}"
        )


# =========================================================
# ENABLE WI-FI
# =========================================================

def enable_wifi():

    return _set_wifi_state(
        RADIO_ON
    )


# =========================================================
# DISABLE WI-FI
# =========================================================

def disable_wifi():

    return _set_wifi_state(
        RADIO_OFF
    )