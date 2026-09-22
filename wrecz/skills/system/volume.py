# =========================================================
# WRECZ VOLUME CONTROL
# Pure ctypes Windows Core Audio implementation
#
# This version intentionally does NOT use pycaw/comtypes for
# IMMDevice.Activate or IAudioEndpointVolume method dispatch.
#
# Reason:
# the environment is throwing:
#
#   TypeError: expected LP_PROPVARIANT instance instead of
#   pointer to PROPVARIANT
#
# That error is coming from the comtypes-generated Core Audio
# wrapper. This implementation calls the Windows COM vtables
# directly with native ctypes signatures instead.
# =========================================================

import ctypes
from ctypes import wintypes


# =========================================================
# WINDOWS / COM CONSTANTS
# =========================================================

HRESULT = ctypes.c_long

S_OK = 0

CLSCTX_ALL = 0x17

# eRender
E_RENDER = 0

# eMultimedia
E_MULTIMEDIA = 1


# =========================================================
# GUID HELPERS
# =========================================================

class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid(
    text
):
    """
    Convert a normal GUID string into the Windows GUID structure.
    """
    import uuid

    value = uuid.UUID(
        text
    )

    fields = value.fields

    return GUID(
        fields[0],
        fields[1],
        fields[2],
        (ctypes.c_ubyte * 8)(
            *value.bytes[8:]
        )
    )


CLSID_MM_DEVICE_ENUMERATOR = _guid(
    "BCDE0395-E52F-467C-8E3D-C4579291692E"
)

IID_IMM_DEVICE_ENUMERATOR = _guid(
    "A95664D2-9614-4F35-A746-DE8DB63617E6"
)

IID_IMM_DEVICE = _guid(
    "D666063F-1587-4E43-81F1-B948E807363F"
)

IID_IAUDIO_ENDPOINT_VOLUME = _guid(
    "5CDF2C82-841E-4546-9722-0CF74078229A"
)


# =========================================================
# PROPVARIANT
# =========================================================
#
# We only need a pointer type for IMMDevice.Activate.
# We do NOT instantiate or manipulate a PROPVARIANT.
# =========================================================

class PROPVARIANT(ctypes.Structure):
    _fields_ = [
        ("vt", wintypes.USHORT),
        ("wReserved1", wintypes.USHORT),
        ("wReserved2", wintypes.USHORT),
        ("wReserved3", wintypes.USHORT),
        ("data", ctypes.c_ubyte * 16),
    ]


# =========================================================
# COM INITIALIZATION
# =========================================================

ole32 = ctypes.OleDLL(
    "ole32"
)

ole32.CoInitializeEx.argtypes = [
    ctypes.c_void_p,
    wintypes.DWORD,
]

ole32.CoInitializeEx.restype = HRESULT

ole32.CoUninitialize.argtypes = []

ole32.CoUninitialize.restype = None


ole32.CoCreateInstance.argtypes = [
    ctypes.POINTER(GUID),
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(GUID),
    ctypes.POINTER(
        ctypes.c_void_p
    ),
]

ole32.CoCreateInstance.restype = HRESULT


# =========================================================
# COM VTABLE HELPERS
# =========================================================

def _vtable(
    interface_ptr
):
    """
    Return the COM vtable for a raw interface pointer.
    """

    address = ctypes.cast(
        interface_ptr,
        ctypes.c_void_p
    ).value

    if not address:
        raise RuntimeError(
            "Received a null COM interface."
        )

    pointer = ctypes.cast(
        address,
        ctypes.POINTER(
            ctypes.POINTER(
                ctypes.c_void_p
            )
        )
    )

    return pointer.contents


def _release(
    interface_ptr
):
    """
    Release a raw COM interface.
    """

    if not interface_ptr:
        return

    try:

        table = _vtable(
            interface_ptr
        )

        release_address = table[2]

        Release = ctypes.WINFUNCTYPE(
            wintypes.ULONG,
            ctypes.c_void_p,
        )(
            release_address
        )

        Release(
            ctypes.cast(
                interface_ptr,
                ctypes.c_void_p
            )
        )

    except Exception:
        # Never mask the original operation error during
        # cleanup.
        pass


# =========================================================
# GET DEFAULT AUDIO ENDPOINT
# =========================================================

def _get_default_endpoint_device():

    enumerator = ctypes.c_void_p()
    device = ctypes.c_void_p()

    initialized = False

    try:

        init_result = ole32.CoInitializeEx(
            None,
            0x2,  # COINIT_APARTMENTTHREADED
        )

        # S_OK or S_FALSE both mean COM is usable.
        if init_result in (0, 1):
            initialized = True

        result = ole32.CoCreateInstance(
            ctypes.byref(
                CLSID_MM_DEVICE_ENUMERATOR
            ),
            None,
            CLSCTX_ALL,
            ctypes.byref(
                IID_IMM_DEVICE_ENUMERATOR
            ),
            ctypes.byref(
                enumerator
            ),
        )

        if result != S_OK:

            raise OSError(
                "CoCreateInstance(IMMDeviceEnumerator) "
                f"failed: HRESULT 0x"
                f"{result & 0xFFFFFFFF:08X}"
            )

        table = _vtable(
            enumerator
        )

        # IMMDeviceEnumerator::GetDefaultAudioEndpoint
        # vtable index 4
        get_default_address = table[4]

        GetDefaultAudioEndpoint = ctypes.WINFUNCTYPE(
            HRESULT,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(
                ctypes.c_void_p
            ),
        )(
            get_default_address
        )

        result = GetDefaultAudioEndpoint(
            ctypes.cast(
                enumerator,
                ctypes.c_void_p
            ),
            E_RENDER,
            E_MULTIMEDIA,
            ctypes.byref(
                device
            ),
        )

        if result != S_OK:

            raise OSError(
                "GetDefaultAudioEndpoint failed: "
                f"HRESULT 0x"
                f"{result & 0xFFFFFFFF:08X}"
            )

        return (
            device,
            initialized
        )

    except Exception:

        _release(
            enumerator
        )

        if initialized:
            ole32.CoUninitialize()

        raise


# =========================================================
# ACTIVATE IAudioEndpointVolume
# =========================================================

def _get_endpoint_volume():

    device = None
    enumerator = None
    initialized = False

    try:

        device, initialized = (
            _get_default_endpoint_device()
        )

        # Get the IMMDeviceEnumerator pointer again is not
        # needed; _get_default_endpoint_device returned only
        # the device. It already handled initialization.

        table = _vtable(
            device
        )

        # IMMDevice::Activate
        # vtable index 3
        activate_address = table[3]

        Activate = ctypes.WINFUNCTYPE(
            HRESULT,
            ctypes.c_void_p,
            ctypes.POINTER(GUID),
            wintypes.DWORD,
            ctypes.POINTER(
                PROPVARIANT
            ),
            ctypes.POINTER(
                ctypes.c_void_p
            ),
        )(
            activate_address
        )

        endpoint_volume = ctypes.c_void_p()

        # CRITICAL:
        # pActivationParams is explicitly NULL.
        #
        # This is passed through our ctypes declaration,
        # not through comtypes' PROPVARIANT wrapper.
        result = Activate(
            ctypes.cast(
                device,
                ctypes.c_void_p
            ),
            ctypes.byref(
                IID_IAUDIO_ENDPOINT_VOLUME
            ),
            CLSCTX_ALL,
            None,
            ctypes.byref(
                endpoint_volume
            ),
        )

        if result != S_OK:

            raise OSError(
                "IMMDevice.Activate(IAudioEndpointVolume) "
                f"failed: HRESULT 0x"
                f"{result & 0xFFFFFFFF:08X}"
            )

        return (
            endpoint_volume,
            device,
            initialized
        )

    except Exception:

        _release(
            device
        )

        if initialized:
            ole32.CoUninitialize()

        raise


# =========================================================
# AUDIO ENDPOINT VOLUME METHODS
# =========================================================
#
# IAudioEndpointVolume vtable:
#
# 0 QueryInterface
# 1 AddRef
# 2 Release
# 3 RegisterControlChangeNotify
# 4 UnregisterControlChangeNotify
# 5 GetChannelCount
# 6 SetMasterVolumeLevel
# 7 SetMasterVolumeLevelScalar
# 8 GetMasterVolumeLevel
# 9 GetMasterVolumeLevelScalar
# 10 SetChannelVolumeLevel
# 11 SetChannelVolumeLevelScalar
# 12 GetChannelVolumeLevel
# 13 GetChannelVolumeLevelScalar
# 14 SetMute
# 15 GetMute
# 16 GetVolumeStepInfo
# 17 VolumeStepUp
# 18 VolumeStepDown
# =========================================================


def _get_scalar(
    endpoint
):

    table = _vtable(
        endpoint
    )

    address = table[9]

    GetMasterVolumeLevelScalar = (
        ctypes.WINFUNCTYPE(
            HRESULT,
            ctypes.c_void_p,
            ctypes.POINTER(
                ctypes.c_float
            ),
        )(address)
    )

    value = ctypes.c_float()

    result = GetMasterVolumeLevelScalar(
        ctypes.cast(
            endpoint,
            ctypes.c_void_p
        ),
        ctypes.byref(
            value
        ),
    )

    if result != S_OK:

        raise OSError(
            "GetMasterVolumeLevelScalar failed: "
            f"HRESULT 0x"
            f"{result & 0xFFFFFFFF:08X}"
        )

    return float(
        value.value
    )


def _set_scalar(
    endpoint,
    value
):

    table = _vtable(
        endpoint
    )

    address = table[7]

    SetMasterVolumeLevelScalar = (
        ctypes.WINFUNCTYPE(
            HRESULT,
            ctypes.c_void_p,
            ctypes.c_float,
            ctypes.c_void_p,
        )(address)
    )

    result = SetMasterVolumeLevelScalar(
        ctypes.cast(
            endpoint,
            ctypes.c_void_p
        ),
        ctypes.c_float(
            value
        ),
        None,
    )

    if result != S_OK:

        raise OSError(
            "SetMasterVolumeLevelScalar failed: "
            f"HRESULT 0x"
            f"{result & 0xFFFFFFFF:08X}"
        )


def _get_mute(
    endpoint
):

    table = _vtable(
        endpoint
    )

    address = table[15]

    GetMute = ctypes.WINFUNCTYPE(
        HRESULT,
        ctypes.c_void_p,
        ctypes.POINTER(
            wintypes.BOOL
        ),
    )(address)

    value = wintypes.BOOL()

    result = GetMute(
        ctypes.cast(
            endpoint,
            ctypes.c_void_p
        ),
        ctypes.byref(
            value
        ),
    )

    if result != S_OK:

        raise OSError(
            "GetMute failed: "
            f"HRESULT 0x"
            f"{result & 0xFFFFFFFF:08X}"
        )

    return bool(
        value.value
    )


def _set_mute(
    endpoint,
    muted
):

    table = _vtable(
        endpoint
    )

    address = table[14]

    SetMute = ctypes.WINFUNCTYPE(
        HRESULT,
        ctypes.c_void_p,
        wintypes.BOOL,
        ctypes.c_void_p,
    )(address)

    result = SetMute(
        ctypes.cast(
            endpoint,
            ctypes.c_void_p
        ),
        wintypes.BOOL(
            bool(muted)
        ),
        None,
    )

    if result != S_OK:

        raise OSError(
            "SetMute failed: "
            f"HRESULT 0x"
            f"{result & 0xFFFFFFFF:08X}"
        )


# =========================================================
# PUBLIC API
# =========================================================

def get_volume():

    endpoint = None
    device = None
    initialized = False

    try:

        (
            endpoint,
            device,
            initialized
        ) = _get_endpoint_volume()

        scalar = _get_scalar(
            endpoint
        )

        percentage = round(
            max(
                0.0,
                min(
                    1.0,
                    scalar
                )
            )
            * 100.0
        )

        return (
            True,
            percentage
        )

    except Exception as error:

        return (
            False,
            f"Could not read volume: {error}"
        )

    finally:

        _release(
            endpoint
        )

        _release(
            device
        )

        if initialized:
            ole32.CoUninitialize()


def set_volume(
    percentage
):

    try:

        percentage = float(
            percentage
        )

    except (
        TypeError,
        ValueError
    ):

        return (
            False,
            "Volume must be a number between 0 and 100."
        )

    percentage = max(
        0.0,
        min(
            100.0,
            percentage
        )
    )

    endpoint = None
    device = None
    initialized = False

    try:

        (
            endpoint,
            device,
            initialized
        ) = _get_endpoint_volume()

        _set_scalar(
            endpoint,
            percentage / 100.0
        )

        return (
            True,
            f"Volume set to {round(percentage)}%."
        )

    except Exception as error:

        return (
            False,
            f"Could not set volume: {error}"
        )

    finally:

        _release(
            endpoint
        )

        _release(
            device
        )

        if initialized:
            ole32.CoUninitialize()


def increase_volume(
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
        amount = 10.0

    success, current = (
        get_volume()
    )

    if not success:

        return (
            False,
            current
        )

    return set_volume(
        min(
            100.0,
            current + amount
        )
    )


def decrease_volume(
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
        amount = 10.0

    success, current = (
        get_volume()
    )

    if not success:

        return (
            False,
            current
        )

    return set_volume(
        max(
            0.0,
            current - amount
        )
    )


def mute():

    endpoint = None
    device = None
    initialized = False

    try:

        (
            endpoint,
            device,
            initialized
        ) = _get_endpoint_volume()

        _set_mute(
            endpoint,
            True
        )

        return (
            True,
            "Volume muted."
        )

    except Exception as error:

        return (
            False,
            f"Could not mute volume: {error}"
        )

    finally:

        _release(
            endpoint
        )

        _release(
            device
        )

        if initialized:
            ole32.CoUninitialize()


def unmute():

    endpoint = None
    device = None
    initialized = False

    try:

        (
            endpoint,
            device,
            initialized
        ) = _get_endpoint_volume()

        _set_mute(
            endpoint,
            False
        )

        return (
            True,
            "Volume unmuted."
        )

    except Exception as error:

        return (
            False,
            f"Could not unmute volume: {error}"
        )

    finally:

        _release(
            endpoint
        )

        _release(
            device
        )

        if initialized:
            ole32.CoUninitialize()


def toggle_mute():

    endpoint = None
    device = None
    initialized = False

    try:

        (
            endpoint,
            device,
            initialized
        ) = _get_endpoint_volume()

        muted = _get_mute(
            endpoint
        )

        _set_mute(
            endpoint,
            not muted
        )

        return (
            True,
            "Volume unmuted."
            if muted
            else
            "Volume muted."
        )

    except Exception as error:

        return (
            False,
            f"Could not toggle volume: {error}"
        )

    finally:

        _release(
            endpoint
        )

        _release(
            device
        )

        if initialized:
            ole32.CoUninitialize()