import asyncio

from winrt.windows.devices.radios import (
    Radio,
    RadioKind,
    RadioState
)


# =========================================================
# INTERNAL RADIO FINDER
# =========================================================

async def _get_bluetooth_radio():

    radios = await Radio.get_radios_async()

    for radio in radios:

        if radio.kind == RadioKind.BLUETOOTH:

            return radio

    return None


# =========================================================
# RUN ASYNC FUNCTION
# =========================================================

def _run_async(coro):

    try:

        return asyncio.run(coro)

    except Exception as error:

        return False, str(error)


# =========================================================
# GET BLUETOOTH STATUS
# =========================================================

async def _get_status():

    radio = await _get_bluetooth_radio()


    if radio is None:

        return (
            False,
            "Bluetooth radio was not found."
        )


    state = radio.state


    if state == RadioState.ON:

        enabled = True

        status = "ON"


    elif state == RadioState.OFF:

        enabled = False

        status = "OFF"


    else:

        enabled = False

        status = str(state)


    return (

        True,

        {

            "name": "Bluetooth",

            "state": status,

            "enabled": enabled

        }

    )


def get_bluetooth_status():

    return _run_async(
        _get_status()
    )


# =========================================================
# ENABLE BLUETOOTH
# =========================================================

async def _enable():

    radio = await _get_bluetooth_radio()


    if radio is None:

        return (
            False,
            "Bluetooth radio was not found."
        )


    if radio.state == RadioState.ON:

        return (
            True,
            "Bluetooth is already on."
        )


    result = await radio.set_state_async(
        RadioState.ON
    )


    # Give Windows a moment to apply the change.
    await asyncio.sleep(
        0.5
    )


    if radio.state == RadioState.ON:

        return (
            True,
            "Bluetooth turned on successfully."
        )


    return (
        False,
        f"Windows returned: {result}"
    )


def enable_bluetooth():

    return _run_async(
        _enable()
    )


# =========================================================
# DISABLE BLUETOOTH
# =========================================================

async def _disable():

    radio = await _get_bluetooth_radio()


    if radio is None:

        return (
            False,
            "Bluetooth radio was not found."
        )


    if radio.state == RadioState.OFF:

        return (
            True,
            "Bluetooth is already off."
        )


    result = await radio.set_state_async(
        RadioState.OFF
    )


    await asyncio.sleep(
        0.5
    )


    if radio.state == RadioState.OFF:

        return (
            True,
            "Bluetooth turned off successfully."
        )


    return (
        False,
        f"Windows returned: {result}"
    )


def disable_bluetooth():

    return _run_async(
        _disable()
    )


# =========================================================
# DIRECT TEST
# =========================================================

if __name__ == "__main__":

    print(
        get_bluetooth_status()
    )