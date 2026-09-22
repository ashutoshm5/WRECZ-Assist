import ctypes
import json
import threading
import os
import time

from ctypes import wintypes


# =========================================================
# WRECZ WINDOW OWNERSHIP CORE
# =========================================================
#
# SECURITY MODEL
#
# Wrecz controls WINDOWS, not application processes.
#
# Wrecz NEVER uses:
#
#     taskkill /IM
#     taskkill /T
#     taskkill /PID
#
# Instead:
#
#     OPEN
#       ↓
#     Take desktop snapshot
#       ↓
#     Launch application
#       ↓
#     Detect newly-created HWND
#       ↓
#     Verify ownership
#       ↓
#     Register HWND
#
#     CLOSE
#       ↓
#     Retrieve Wrecz-owned HWND
#       ↓
#     Verify ownership again
#       ↓
#     Send WM_CLOSE
#       ↓
#     Verify that SAME HWND disappeared
#
# This means:
#
#     User's Chrome window     → untouched
#     Wrecz's Chrome window    → closable
#
#     User's Figma window      → untouched
#     Wrecz's Figma window     → closable
#
#     User's Claude window     → untouched
#     Wrecz's Claude window    → closable
#
# =========================================================


if os.name != "nt":
    raise RuntimeError(
        "Wrecz Window Manager currently requires Windows."
    )


# =========================================================
# WINDOWS API
# =========================================================

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


EnumWindowsProc = ctypes.WINFUNCTYPE(
    wintypes.BOOL,
    wintypes.HWND,
    wintypes.LPARAM
)


WM_CLOSE = 0x0010


# =========================================================
# PACKAGED WINDOW IDENTITY
# =========================================================
#
# Windows packaged applications can share the same
# ApplicationFrameHost.exe PID.
#
# Therefore PID alone is NOT a sufficient identity.
#
# We retrieve the AppUserModelID directly from the HWND
# using the Windows Shell Property Store.
#
# =========================================================

WM_SYSCOMMAND = 0x0112
SC_CLOSE = 0xF060

COINIT_APARTMENTTHREADED = 0x2

S_OK = 0


# ---------------------------------------------------------
# IPropertyStore
# ---------------------------------------------------------

IID_IPROPERTY_STORE = (
    ctypes.c_byte * 16
)(
    0xEB, 0x8E, 0x6D, 0x88,
    0xF2, 0x8C,
    0x46, 0x44,
    0x8D, 0x02,
    0xCD, 0xBA, 0x1D, 0xBD, 0xCF, 0x99
)


# ---------------------------------------------------------
# PKEY_AppUserModel_ID
#
# {9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}, PID 5
# ---------------------------------------------------------

PKEY_APP_USER_MODEL_ID_FMTID = (
    ctypes.c_byte * 16
)(
    0x55, 0x28, 0x4C, 0x9F,
    0x79, 0x9F,
    0x39, 0x4B,
    0xA8, 0xD0,
    0xE1, 0xD4, 0x2D, 0xE1, 0xD5, 0xF3
)


class PROPERTYKEY(ctypes.Structure):

    _fields_ = [

        (
            "fmtid",
            ctypes.c_byte * 16
        ),

        (
            "pid",
            wintypes.DWORD
        )
    ]


# ---------------------------------------------------------
# PROPVARIANT
#
# We only need to read a string property here.
# ---------------------------------------------------------

class PROPVARIANT(ctypes.Structure):

    _fields_ = [

        (
            "vt",
            wintypes.USHORT
        ),

        (
            "wReserved1",
            wintypes.USHORT
        ),

        (
            "wReserved2",
            wintypes.USHORT
        ),

        (
            "wReserved3",
            wintypes.USHORT
        ),

        (
            "data",
            ctypes.c_byte * 16
        )
    ]


# ---------------------------------------------------------
# Windows APIs
# ---------------------------------------------------------

ole32 = ctypes.windll.ole32
shell32 = ctypes.windll.shell32


ole32.CoInitializeEx.argtypes = [
    ctypes.c_void_p,
    wintypes.DWORD
]

ole32.CoInitializeEx.restype = ctypes.c_long

ole32.CoUninitialize.argtypes = []

ole32.CoUninitialize.restype = None


ole32.PropVariantClear.argtypes = [
    ctypes.POINTER(
        PROPVARIANT
    )
]

ole32.PropVariantClear.restype = ctypes.c_long


shell32.SHGetPropertyStoreForWindow.argtypes = [

    wintypes.HWND,

    ctypes.POINTER(
        ctypes.c_byte * 16
    ),

    ctypes.POINTER(
        ctypes.c_void_p
    )
]

shell32.SHGetPropertyStoreForWindow.restype = (
    ctypes.c_long
)

# =========================================================
# WINDOW MANAGER
# =========================================================

class WindowManager:

    def __init__(
        self,
        storage_path=None
    ):

        if storage_path is None:

            project_root = os.path.dirname(
                os.path.dirname(
                    os.path.abspath(
                        __file__
                    )
                )
            )

            storage_path = os.path.join(
                project_root,
                "workspace",
                ".wrecz_windows.json"
            )

        self.storage_path = os.path.abspath(
            storage_path
        )

        self._ensure_storage_directory()

        self.windows = self._load()

        # -------------------------------------------------
        # Remove stale ownership records on startup.
        # -------------------------------------------------

        self.cleanup()


    # =====================================================
    # STORAGE
    # =====================================================

    def _ensure_storage_directory(
        self
    ):

        directory = os.path.dirname(
            self.storage_path
        )

        if directory:

            os.makedirs(
                directory,
                exist_ok=True
            )


    def _load(
        self
    ):

        if not os.path.isfile(
            self.storage_path
        ):

            return {}

        try:

            with open(
                self.storage_path,
                "r",
                encoding="utf-8"
            ) as file:

                data = json.load(file)

            if isinstance(
                data,
                dict
            ):

                return data

        except Exception:

            pass

        return {}


    def _save(
        self
    ):

        temporary_path = (
            self.storage_path
            + ".tmp"
        )

        with open(
            temporary_path,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                self.windows,
                file,
                indent=4
            )

        os.replace(
            temporary_path,
            self.storage_path
        )


    # =====================================================
    # ENUMERATE WINDOWS
    # =====================================================

    def list_windows(
        self
    ):

        windows = []


        def callback(
            hwnd,
            lparam
        ):

            try:

                if not user32.IsWindow(
                    hwnd
                ):

                    return True


                if not user32.IsWindowVisible(
                    hwnd
                ):

                    return True


                length = (
                    user32.GetWindowTextLengthW(
                        hwnd
                    )
                )


                title = ""


                if length > 0:

                    buffer = ctypes.create_unicode_buffer(
                        length + 1
                    )

                    user32.GetWindowTextW(
                        hwnd,
                        buffer,
                        length + 1
                    )

                    title = buffer.value


                process_id = (
                    wintypes.DWORD()
                )


                user32.GetWindowThreadProcessId(
                    hwnd,
                    ctypes.byref(
                        process_id
                    )
                )


                if process_id.value == 0:

                    return True


                windows.append({

                    "hwnd": int(
                        hwnd
                    ),

                    "pid": int(
                        process_id.value
                    ),

                    "title": title

                })


            except Exception:

                pass


            return True


        user32.EnumWindows(
            EnumWindowsProc(
                callback
            ),
            0
        )


        return windows


    # =====================================================
    # GET PROCESS EXECUTABLE
    # =====================================================

    def get_process_executable(
        self,
        pid
    ):

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


        handle = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            int(pid)
        )


        if not handle:

            return None


        try:

            buffer_size = wintypes.DWORD(
                32768
            )

            buffer = ctypes.create_unicode_buffer(
                buffer_size.value
            )


            result = (
                kernel32.QueryFullProcessImageNameW(
                    handle,
                    0,
                    buffer,
                    ctypes.byref(
                        buffer_size
                    )
                )
            )


            if not result:

                return None


            return buffer.value


        finally:

            kernel32.CloseHandle(
                handle
            )


    # =====================================================
    # GET PACKAGE FAMILY NAME
    # =====================================================

    def get_process_package_family(
        self,
        pid
    ):

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

        handle = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            int(pid)
        )

        if not handle:
            return None

        try:
            api = kernel32.GetPackageFamilyName
            api.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(wintypes.DWORD),
                wintypes.LPWSTR
            ]
            api.restype = wintypes.DWORD

            size = wintypes.DWORD(256)
            buffer = ctypes.create_unicode_buffer(
                size.value
            )

            result = api(
                handle,
                ctypes.byref(size),
                buffer
            )

            if result != 0:
                return None

            return buffer.value.strip()

        except Exception:
            return None

        finally:
            kernel32.CloseHandle(handle)


    @staticmethod
    def package_family_from_app_id(
        app_id
    ):

        if not app_id:
            return ""

        return (
            str(app_id)
            .strip()
            .split("!", 1)[0]
            .strip()
        )

    # =====================================================
    # GET AUMID FROM HWND
    # =====================================================
    #
    # This is the critical packaged-app fix.
    #
    # DO NOT use PID alone.
    #
    # Example:
    #
    # Calculator
    #     HWND 1378048
    #     PID  13920
    #
    # Settings
    #     HWND 591734
    #     PID  13920
    #
    # Same PID.
    # Different HWND.
    # Different AppUserModelID.
    #
    # =====================================================

    def get_window_app_user_model_id(
        self,
        hwnd
    ):

        if not hwnd:

            return ""


        if not user32.IsWindow(
            hwnd
        ):

            return ""


        initialized = False


        try:

            # -------------------------------------------------
            # Initialize COM for the current thread.
            # -------------------------------------------------

            result = (
                ole32.CoInitializeEx(
                    None,
                    COINIT_APARTMENTTHREADED
                )
            )


            if result in (
                S_OK,
                1
            ):

                initialized = True


            # -------------------------------------------------
            # Get IPropertyStore for this HWND.
            # -------------------------------------------------

            store = (
                ctypes.c_void_p()
            )


            iid = (
                (ctypes.c_byte * 16)
                .from_buffer_copy(
                    IID_IPROPERTY_STORE
                )
            )


            result = (
                shell32.SHGetPropertyStoreForWindow(

                    wintypes.HWND(
                        int(hwnd)
                    ),

                    ctypes.byref(
                        iid
                    ),

                    ctypes.byref(
                        store
                    )
                )
            )


            if result != S_OK:

                return ""


            if not store.value:

                return ""


            try:

                # -------------------------------------------------
                # IPropertyStore vtable
                #
                # 0 = QueryInterface
                # 1 = AddRef
                # 2 = Release
                # 3 = GetCount
                # 4 = GetAt
                # 5 = GetValue
                # -------------------------------------------------

                vtable = ctypes.cast(

                    store,

                    ctypes.POINTER(
                        ctypes.POINTER(
                            ctypes.c_void_p
                        )
                    )
                ).contents


                get_value_address = (
                    vtable[5]
                )


                GetValue = ctypes.WINFUNCTYPE(

                    ctypes.c_long,

                    ctypes.c_void_p,

                    ctypes.POINTER(
                        PROPERTYKEY
                    ),

                    ctypes.POINTER(
                        PROPVARIANT
                    )

                )(
                    get_value_address
                )


                property_key = PROPERTYKEY()

                ctypes.memmove(

                    property_key.fmtid,

                    PKEY_APP_USER_MODEL_ID_FMTID,

                    16
                )


                property_key.pid = 5


                variant = PROPVARIANT()


                result = GetValue(

                    store,

                    ctypes.byref(
                        property_key
                    ),

                    ctypes.byref(
                        variant
                    )
                )


                if result != S_OK:

                    return ""


                try:

                    # -------------------------------------------------
                    # Common string PROPVARIANT types:
                    #
                    # VT_LPWSTR = 31
                    # VT_BSTR   = 8
                    # -------------------------------------------------

                    vt = (
                        int(
                            variant.vt
                        )
                    )


                    pointer_value = (
                        ctypes.cast(
                            variant.data,
                            ctypes.POINTER(
                                ctypes.c_void_p
                            )
                        )[0]
                    )


                    if not pointer_value:

                        return ""


                    if vt == 31:

                        return (
                            ctypes.wstring_at(
                                pointer_value
                            )
                            .strip()
                            .lower()
                        )


                    if vt == 8:

                        return (
                            ctypes.wstring_at(
                                pointer_value
                            )
                            .strip()
                            .lower()
                        )


                    return ""


                finally:

                    ole32.PropVariantClear(
                        ctypes.byref(
                            variant
                        )
                    )


            finally:

                # -------------------------------------------------
                # Release IPropertyStore.
                # -------------------------------------------------

                vtable = ctypes.cast(

                    store,

                    ctypes.POINTER(
                        ctypes.POINTER(
                            ctypes.c_void_p
                        )
                    )
                ).contents


                release_address = (
                    vtable[2]
                )


                Release = ctypes.WINFUNCTYPE(

                    wintypes.ULONG,

                    ctypes.c_void_p

                )(
                    release_address
                )


                Release(
                    store
                )


        except Exception:

            return ""


        finally:

            if initialized:

                ole32.CoUninitialize()


    # =====================================================
    # NORMALIZE PATH
    # =====================================================

    @staticmethod
    def normalize_path(
        path
    ):

        if not path:

            return ""


        return os.path.normcase(
            os.path.normpath(
                os.path.abspath(
                    path
                )
            )
        )


    # =====================================================
    # NORMALIZE APPLICATION
    # =====================================================

    @staticmethod
    def normalize_application(
        application
    ):

        if application is None:

            return ""


        return (
            str(application)
            .strip()
            .lower()
        )


    # =====================================================
    # SNAPSHOT
    # =====================================================

    def snapshot(
        self
    ):

        return {
            window["hwnd"]: window
            for window in self.list_windows()
        }


    # =====================================================
    # FIND NEW WINDOW
    # =====================================================
    #
    # NORMAL EXE MODE
    #
    # Requires:
    #
    #     HWND did not exist before
    #     +
    #     executable matches
    #
    # This is the strongest ownership check.
    #
    # =====================================================

    def find_new_window(
        self,
        before,
        executable,
        timeout=10.0,
        application=None
    ):

        trusted_executable = (
            self.normalize_path(
                executable
            )
        )


        application = (
            self.normalize_application(
                application
            )
        )


        deadline = (
            time.time()
            + timeout
        )


        while time.time() < deadline:

            current = self.list_windows()


            for window in current:

                hwnd = window["hwnd"]


                # -----------------------------------------
                # Window existed before Wrecz launched it.
                # -----------------------------------------

                if hwnd in before:

                    continue


                # -----------------------------------------
                # Get executable behind this HWND.
                # -----------------------------------------

                window_executable = (
                    self.get_process_executable(
                        window["pid"]
                    )
                )


                if not window_executable:

                    continue


                window_executable = (
                    self.normalize_path(
                        window_executable
                    )
                )


                # -----------------------------------------
                # Exact executable ownership check.
                # -----------------------------------------

                if (
                    trusted_executable
                    and
                    window_executable
                    !=
                    trusted_executable
                ):

                    continue


                return window


            time.sleep(
                0.25
            )


        return None


    # =====================================================
    # FIND NEW WINDOW - FLEXIBLE / PACKAGED MODE
    # =====================================================
    #
    # Used when the application discovery system knows
    # the application but cannot provide a reliable
    # executable path.
    #
    # SECURITY:
    #
    # We STILL require:
    #
    #     1. HWND did not exist before launch
    #     2. Window is visible
    #     3. Window has a valid PID
    #
    # We do NOT grab an arbitrary existing window.
    #
    # If an executable is available, we ALWAYS prefer
    # exact executable matching.
    #
    # =====================================================

    def find_new_application_window(
        self,
        before,
        application=None,
        executable=None,
        app_id=None,
        timeout=10.0
    ):

        trusted_executable = (
            self.normalize_path(
                executable
            )
        )


        application = (
            self.normalize_application(
                application
            )
        )


        deadline = (
            time.time()
            + timeout
        )


        while time.time() < deadline:

            current = self.list_windows()


            new_windows = []


            for window in current:

                hwnd = window["hwnd"]


                # -----------------------------------------
                # NEVER claim an existing window.
                # -----------------------------------------

                if hwnd in before:

                    continue


                if not user32.IsWindow(
                    hwnd
                ):

                    continue


                if not user32.IsWindowVisible(
                    hwnd
                ):

                    continue


                if not window.get(
                    "pid",
                    0
                ):

                    continue


                new_windows.append(
                    window
                )


            # -------------------------------------------------
            # First preference:
            #
            # exact executable match.
            # -------------------------------------------------

            if trusted_executable:

                for window in new_windows:

                    window_executable = (
                        self.get_process_executable(
                            window["pid"]
                        )
                    )


                    if not window_executable:

                        continue


                    window_executable = (
                        self.normalize_path(
                            window_executable
                        )
                    )


                    if (
                        window_executable
                        ==
                        trusted_executable
                    ):

                        return window


            # -------------------------------------------------
            # Packaged AppID / package-family check.
            # -------------------------------------------------

            if app_id:

                trusted_family = (
                    self.package_family_from_app_id(
                        app_id
                    )
                    .lower()
                )

                if trusted_family:

                    for window in new_windows:

                        family = (
                            self.get_process_package_family(
                                window["pid"]
                            )
                        )

                        if (
                            family
                            and
                            family.lower()
                            ==
                            trusted_family
                        ):
                            return window


            # -------------------------------------------------
            # Packaged / executable-less fallback.
            #
            # We don't have an executable identity, so
            # we use the newly-created HWND itself as the
            # ownership boundary.
            #
            # A completely blank window is rejected.
            # -------------------------------------------------

            if new_windows:

                titled_windows = [

                    window

                    for window in new_windows

                    if (
                        str(
                            window.get(
                                "title",
                                ""
                            )
                        ).strip()
                    )

                ]


                if titled_windows:

                    # -------------------------------------
                    # If only one new visible titled window
                    # appeared, it is the safest candidate.
                    # -------------------------------------

                    if len(
                        titled_windows
                    ) == 1:

                        return titled_windows[0]


                    # -------------------------------------
                    # If application name appears in a title,
                    # prefer that window.
                    # -------------------------------------

                    if application:

                        application_tokens = (
                            application
                            .replace(
                                "-",
                                " "
                            )
                            .replace(
                                "_",
                                " "
                            )
                            .split()
                        )


                        for window in titled_windows:

                            title = (
                                window.get(
                                    "title",
                                    ""
                                )
                                .lower()
                            )


                            if all(
                                token in title
                                for token
                                in application_tokens
                                if token
                            ):

                                return window


            time.sleep(
                0.25
            )


        return None


    # =====================================================
    # REGISTER WINDOW
    # =====================================================

    def register_window(
        self,
        application,
        window,
        executable="",
        app_type="WIN32",
        app_id=""
    ):

        application = (
            self.normalize_application(
                application
            )
        )


        if not application:

            return False


        if not window:

            return False


        hwnd = int(
            window.get(
                "hwnd",
                0
            )
        )


        pid = int(
            window.get(
                "pid",
                0
            )
        )


        if not hwnd or not pid:

            return False


        normalized_executable = (
            self.normalize_path(
                executable
            )
            if executable
            else ""
        )


        self.windows[application] = {

            "application": application,

            "hwnd": hwnd,

            "pid": pid,

            "title": window.get(
                "title",
                ""
            ),

            "executable": (
                normalized_executable
            ),

            "app_type": (
                str(
                    app_type
                )
                .strip()
                .upper()
            ),

            "app_id": (
                str(
                    app_id
                )
                .strip()
            ),

            "created_at": time.time(),

            "owned_by_wrecz": True

        }


        self._save()


        return True


    # =====================================================
    # REGISTER PACKAGED WINDOW
    # =====================================================

    def register_packaged_window(
        self,
        application,
        window,
        app_id=""
    ):

        return self.register_window(

            application=application,

            window=window,

            executable="",

            app_type="PACKAGED",

            app_id=app_id
        )


    # =====================================================
    # GET OWNED WINDOW
    # =====================================================

    def get_owned_window(
        self,
        application
    ):

        application = (
            self.normalize_application(
                application
            )
        )


        record = (
            self.windows.get(
                application
            )
        )


        if not record:

            return None


        hwnd = int(
            record.get(
                "hwnd",
                0
            )
        )


        if not hwnd:

            self.forget_window(
                application
            )

            return None


        if not user32.IsWindow(
            hwnd
        ):

            self.forget_window(
                application
            )

            return None


        return record


    # =====================================================
    # VERIFY OWNERSHIP
    # =====================================================
    #
    # WIN32:
    #
    #     HWND
    #      ↓
    #     PID
    #      ↓
    #     executable
    #
    # PACKAGED:
    #
    #     HWND
    #      ↓
    #     PID
    #      ↓
    #     stored packaged PID
    #
    # The packaged path intentionally does NOT use
    # taskkill or process-wide matching.
    #
    # =====================================================

    def verify_ownership(
        self,
        application
    ):

        record = (
            self.get_owned_window(
                application
            )
        )


        if not record:

            return False


        hwnd = int(
            record["hwnd"]
        )


        process_id = (
            wintypes.DWORD()
        )


        user32.GetWindowThreadProcessId(

            hwnd,

            ctypes.byref(
                process_id
            )
        )


        if process_id.value == 0:

            return False


        stored_pid = int(
            record.get(
                "pid",
                0
            )
        )


        # -------------------------------------------------
        # PID must NEVER change.
        # -------------------------------------------------

        if (
            process_id.value
            !=
            stored_pid
        ):

            return False


        stored_executable = (
            record.get(
                "executable",
                ""
            )
        )


        # -------------------------------------------------
        # NORMAL WIN32 APPLICATION
        # -------------------------------------------------

        if stored_executable:

            current_executable = (
                self.get_process_executable(
                    process_id.value
                )
            )


            if not current_executable:

                return False


            current_executable = (
                self.normalize_path(
                    current_executable
                )
            )


            stored_executable = (
                self.normalize_path(
                    stored_executable
                )
            )


            return (
                current_executable
                ==
                stored_executable
            )


        # -------------------------------------------------
        # PACKAGED / EXECUTABLE-LESS APPLICATION
        # -------------------------------------------------
        #
        # For these windows the ownership identity is:
        #
        #     HWND + original PID
        #
        # This prevents Wrecz from accidentally closing
        # another window whose PID is different.
        #
        # We deliberately DO NOT search for another process
        # with the same executable name.
        # -------------------------------------------------

        app_type = (
            str(
                record.get(
                    "app_type",
                    ""
                )
            )
            .strip()
            .upper()
        )


        if app_type == "PACKAGED":

            stored_app_id = (
                str(
                    record.get(
                        "app_id",
                        ""
                    )
                )
                .strip()
            )

            if stored_app_id:

                trusted_family = (
                    self.package_family_from_app_id(
                        stored_app_id
                    )
                    .lower()
                )

                if trusted_family:

                    current_family = (
                        self.get_process_package_family(
                            process_id.value
                        )
                    )

                    if current_family:
                        return (
                            current_family.lower()
                            ==
                            trusted_family
                        )

            return True


        # -------------------------------------------------
        # Unknown executable-less record.
        #
        # Fail closed.
        # -------------------------------------------------

        return False


    # =====================================================
    # PROCESS TREE / INSTANCE IDENTITY
    # =====================================================

    def get_process_parent_map(self):
        """Return {pid: parent_pid} using Toolhelp32Snapshot."""
        TH32CS_SNAPPROCESS = 0x00000002
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        kernel32.Process32FirstW.restype = wintypes.BOOL
        kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        kernel32.Process32NextW.restype = wintypes.BOOL

        handle = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if not handle or handle == INVALID_HANDLE_VALUE:
            return {}
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            result = {}
            if kernel32.Process32FirstW(handle, ctypes.byref(entry)):
                while True:
                    result[int(entry.th32ProcessID)] = {
                        "pid": int(entry.th32ProcessID),
                        "parent_pid": int(entry.th32ParentProcessID),
                        "executable_name": str(entry.szExeFile),
                    }
                    if not kernel32.Process32NextW(handle, ctypes.byref(entry)):
                        break
            return result
        finally:
            kernel32.CloseHandle(handle)

    def get_process_tree(self, root_pid):
        processes = self.get_process_parent_map()
        root_pid = int(root_pid)
        tree = []
        stack = [root_pid]
        while stack:
            pid = stack.pop()
            node = processes.get(pid)
            if not node:
                continue
            tree.append(dict(node))
            children = [p for p, info in processes.items() if info.get("parent_pid") == pid]
            stack.extend(children)
        return tree

        # =====================================================
    # FIND EXISTING APPLICATION WINDOW
    # =====================================================
    #
    # Universal application-window resolver.
    #
    # WIN32:
    #
    #     Application
    #          ↓
    #     exact executable
    #          ↓
    #     PID
    #          ↓
    #     HWND
    #
    # PACKAGED:
    #
    #     Application
    #          ↓
    #     AppID / AUMID
    #          ↓
    #     enumerate HWNDs
    #          ↓
    #     HWND AppUserModelID
    #          ↓
    #     exact match
    #
    # =====================================================

    def find_existing_window(
        self,
        application
    ):

        try:

            from security.application_discovery import (
                ApplicationDiscovery
            )


            discovery = (
                ApplicationDiscovery()
            )


            candidates = (
                discovery.discover(
                    application
                )
            )


            if not candidates:

                return (
                    None,
                    None
                )


            windows = (
                self.list_windows()
            )


            # =================================================
            # TRY EACH DISCOVERED APPLICATION IDENTITY
            # =================================================

            for candidate in candidates:

                app_type = str(
                    getattr(
                        candidate,
                        "app_type",
                        "WIN32"
                    )
                ).strip().upper()


                # =============================================
                # PACKAGED APPLICATION
                # =============================================

                if app_type == "PACKAGED":

                    expected_aumid = str(
                        getattr(
                            candidate,
                            "app_id",
                            ""
                        )
                    ).strip().lower()


                    expected_family = str(
                        getattr(
                            candidate,
                            "package_family",
                            ""
                        )
                    ).strip().lower()


                    if (
                        not expected_aumid
                        and
                        not expected_family
                    ):

                        continue


                    # -----------------------------------------
                    # IMPORTANT:
                    #
                    # Do NOT identify the app from PID.
                    #
                    # Calculator and Settings can share
                    # ApplicationFrameHost.exe.
                    # -----------------------------------------

                    for window in windows:

                        hwnd = int(
                            window.get(
                                "hwnd",
                                0
                            )
                        )


                        if not hwnd:

                            continue


                        if not user32.IsWindow(
                            hwnd
                        ):

                            continue


                        if not user32.IsWindowVisible(
                            hwnd
                        ):

                            continue


                        window_aumid = (
                            self.get_window_app_user_model_id(
                                hwnd
                            )
                        )


                        if not window_aumid:

                            continue


                        # -------------------------------------
                        # Strongest match:
                        #
                        # exact AUMID
                        # -------------------------------------

                        if (
                            expected_aumid
                            and
                            window_aumid
                            ==
                            expected_aumid
                        ):

                            return (
                                window,
                                candidate
                            )


                        # -------------------------------------
                        # Secondary match:
                        #
                        # package family prefix.
                        #
                        # This handles cases where Windows
                        # exposes a slightly different AUMID
                        # representation.
                        # -------------------------------------

                        if (
                            expected_family
                            and
                            window_aumid.startswith(
                                expected_family
                                + "!"
                            )
                        ):

                            return (
                                window,
                                candidate
                            )


                    continue


                # =============================================
                # NORMAL WIN32 APPLICATION
                # =============================================

                expected_executable = (
                    self.normalize_path(
                        getattr(
                            candidate,
                            "executable",
                            ""
                        )
                    )
                )


                if not expected_executable:

                    continue


                for window in windows:

                    hwnd = int(
                        window.get(
                            "hwnd",
                            0
                        )
                    )


                    pid = int(
                        window.get(
                            "pid",
                            0
                        )
                    )


                    if not hwnd or not pid:

                        continue


                    if not user32.IsWindow(
                        hwnd
                    ):

                        continue


                    if not user32.IsWindowVisible(
                        hwnd
                    ):

                        continue


                    actual_executable = (
                        self.get_process_executable(
                            pid
                        )
                    )


                    if not actual_executable:

                        continue


                    actual_executable = (
                        self.normalize_path(
                            actual_executable
                        )
                    )


                    if (
                        actual_executable
                        ==
                        expected_executable
                    ):

                        return (
                            window,
                            candidate
                        )


            return (
                None,
                None
            )


        except Exception:

            return (
                None,
                None
            )
       # =====================================================
    # CLOSE EXISTING APPLICATION WINDOW
    # =====================================================
    #
    # Uses the verified HWND returned by
    # find_existing_window().
    #
    # No taskkill.
    # No process termination.
    #
    # =====================================================

    def close_existing_window(
        self,
        application
    ):

        window, candidate = (
            self.find_existing_window(
                application
            )
        )


        if not window or not candidate:

            return (

                False,

                (
                    f"Wrecz could not find a "
                    f"verified visible window for "
                    f"'{application}'."
                )
            )


        hwnd = int(
            window["hwnd"]
        )


        pid = int(
            window["pid"]
        )


        if not hwnd or not pid:

            return (

                False,

                "The application window "
                "could not be verified."
            )


        # =================================================
        # FINAL HWND VALIDATION
        # =================================================

        if not user32.IsWindow(
            hwnd
        ):

            return (

                False,

                "The application window "
                "no longer exists."
            )


        if not user32.IsWindowVisible(
            hwnd
        ):

            return (

                False,

                "The application window "
                "is no longer visible."
            )


        # =================================================
        # FINAL PID VALIDATION
        # =================================================

        current_pid = (
            wintypes.DWORD()
        )


        user32.GetWindowThreadProcessId(

            hwnd,

            ctypes.byref(
                current_pid
            )
        )


        if (
            current_pid.value
            !=
            pid
        ):

            return (

                False,

                "Window PID changed "
                "before closing."
            )


        # =================================================
        # FINAL APPLICATION IDENTITY CHECK
        # =================================================

        app_type = str(
            getattr(
                candidate,
                "app_type",
                "WIN32"
            )
        ).strip().upper()


        if app_type == "PACKAGED":

            expected_aumid = str(
                getattr(
                    candidate,
                    "app_id",
                    ""
                )
            ).strip().lower()


            expected_family = str(
                getattr(
                    candidate,
                    "package_family",
                    ""
                )
            ).strip().lower()


            actual_aumid = (
                self.get_window_app_user_model_id(
                    hwnd
                )
            )


            if not actual_aumid:

                return (

                    False,

                    (
                        "Wrecz could not read "
                        "the AppUserModelID from "
                        "the application window."
                    )
                )


            # -------------------------------------------------
            # Exact identity
            # -------------------------------------------------

            identity_matches = False


            if (
                expected_aumid
                and
                actual_aumid
                ==
                expected_aumid
            ):

                identity_matches = True


            # -------------------------------------------------
            # Package-family fallback
            # -------------------------------------------------

            if (
                not identity_matches
                and
                expected_family
                and
                actual_aumid.startswith(
                    expected_family
                    + "!"
                )
            ):

                identity_matches = True


            if not identity_matches:

                return (

                    False,

                    (
                        "Packaged application "
                        "window identity verification "
                        "failed."
                    )
                )


        else:

            # -------------------------------------------------
            # WIN32 executable verification
            # -------------------------------------------------

            expected_executable = (
                self.normalize_path(
                    getattr(
                        candidate,
                        "executable",
                        ""
                    )
                )
            )


            actual_executable = (
                self.get_process_executable(
                    pid
                )
            )


            if (
                not actual_executable
                or
                not expected_executable
                or
                self.normalize_path(
                    actual_executable
                )
                !=
                expected_executable
            ):

                return (

                    False,

                    (
                        "Application executable "
                        "verification failed."
                    )
                )


        # =================================================
        # CLOSE ATTEMPT 1
        #
        # Normal Windows close.
        # =================================================

        if not user32.PostMessageW(

            hwnd,

            WM_CLOSE,

            0,

            0

        ):

            return (

                False,

                "Windows rejected the "
                "close request."
            )


        # =================================================
        # WAIT FOR NORMAL CLOSE
        # =================================================

        deadline = (
            time.time()
            + 5.0
        )


        while time.time() < deadline:

            if not user32.IsWindow(
                hwnd
            ):

                return (

                    True,

                    (
                        f"{application} "
                        f"closed successfully."
                    )
                )


            time.sleep(
                0.25
            )


        # =================================================
        # CLOSE ATTEMPT 2
        #
        # Some applications respond better to
        # SC_CLOSE than directly to WM_CLOSE.
        #
        # Still only the verified HWND.
        # =================================================

        user32.PostMessageW(

            hwnd,

            WM_SYSCOMMAND,

            SC_CLOSE,

            0
        )


        # =================================================
        # FINAL WAIT
        # =================================================

        deadline = (
            time.time()
            + 5.0
        )


        while time.time() < deadline:

            if not user32.IsWindow(
                hwnd
            ):

                return (

                    True,

                    (
                        f"{application} "
                        f"closed successfully."
                    )
                )


            time.sleep(
                0.25
            )


        return (

            False,

            (
                f"Wrecz sent close requests to "
                f"{application}, but the verified "
                f"window did not close."
            )
        )

    # =====================================================
    # CLOSE OWNED WINDOW
    # =====================================================
    #
    # IMPORTANT:
    #
    # This sends WM_CLOSE ONLY to the exact HWND Wrecz
    # registered.
    #
    # It does NOT:
    #
    #     terminate the process
    #     kill the process tree
    #     close other windows
    #
    # =====================================================

    def close_owned_window(
        self,
        application
    ):

        if not self.verify_ownership(
            application
        ):

            return (

                False,

                "Wrecz does not have a verified "
                "owned window for this application."
            )


        record = (
            self.get_owned_window(
                application
            )
        )


        if not record:

            return (

                False,

                "The Wrecz-owned window no longer exists."
            )


        hwnd = int(
            record["hwnd"]
        )


        # -------------------------------------------------
        # Final ownership check immediately before close.
        # -------------------------------------------------

        if not self.verify_ownership(
            application
        ):

            return (

                False,

                "Window ownership verification failed "
                "immediately before closing."
            )


        # -------------------------------------------------
        # NORMAL WINDOWS CLOSE REQUEST
        # -------------------------------------------------

        result = user32.PostMessageW(

            hwnd,

            WM_CLOSE,

            0,

            0
        )


        if not result:

            return (

                False,

                "Windows rejected the close request."
            )


        return (

            True,

            "Close request sent to the Wrecz-owned window."
        )


    # =====================================================
    # VERIFY WINDOW CLOSED
    # =====================================================

    def verify_closed(
        self,
        application,
        timeout=8.0
    ):

        application = (
            self.normalize_application(
                application
            )
        )


        record = (
            self.windows.get(
                application
            )
        )


        if not record:

            return True


        hwnd = int(
            record.get(
                "hwnd",
                0
            )
        )


        if not hwnd:

            self.forget_window(
                application
            )

            return True


        deadline = (
            time.time()
            + timeout
        )


        while time.time() < deadline:

            if not user32.IsWindow(
                hwnd
            ):

                self.forget_window(
                    application
                )

                return True


            time.sleep(
                0.25
            )


        return False


    # =====================================================
    # VERIFY WINDOW STILL EXISTS
    # =====================================================

    def verify_open(
        self,
        application
    ):

        record = (
            self.get_owned_window(
                application
            )
        )


        if not record:

            return False


        return self.verify_ownership(
            application
        )


    # =====================================================
    # GET OWNED WINDOW INFO
    # =====================================================

    def get_owned_window_info(
        self,
        application
    ):

        record = (
            self.get_owned_window(
                application
            )
        )


        if not record:

            return None


        return dict(
            record
        )


    # =====================================================
    # FORGET WINDOW
    # =====================================================

    def forget_window(
        self,
        application
    ):

        application = (
            self.normalize_application(
                application
            )
        )


        if application in self.windows:

            del self.windows[
                application
            ]


            self._save()


    # =====================================================
    # CLEAR INVALID OWNERSHIP RECORDS
    # =====================================================

    def cleanup(
        self
    ):

        stale = []


        for application in list(
            self.windows.keys()
        ):

            if not self.verify_ownership(
                application
            ):

                stale.append(
                    application
                )


        for application in stale:

            self.forget_window(
                application
            )


        return len(
            stale
        )


# =========================================================
# SHARED REGISTRY
# =========================================================
#
# One WindowManager per process, deliberately.
#
# WindowManager loads its state once in __init__ and then keeps it in
# memory. Separate instances therefore drift apart the moment one of them
# registers a window: skills/apps.py would register a window that
# core/router.py and security/verification.py never see, so opening an
# application "could not be verified" and closing it "could not find a
# verified visible window" - even though the open succeeded.
#
# Anything needing the registry must go through get_window_manager().
# =========================================================

_SHARED_LOCK = threading.Lock()
_SHARED_MANAGER = None


def get_window_manager():
    """Return the process-wide window registry."""

    global _SHARED_MANAGER

    with _SHARED_LOCK:

        if _SHARED_MANAGER is None:
            _SHARED_MANAGER = WindowManager()

        return _SHARED_MANAGER
