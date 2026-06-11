import traceback

import sublime
import sublime_plugin

SETTINGS_FILE = "Focus Mode Window.sublime-settings"

DEFAULT_COLOR_SCHEME = "Packages/FocusModeWindow/Focus Mode Window.sublime-color-scheme"

# State is persisted in window/view settings (not just a module-global dict) so
# that toggling still works after a plugin reload. A module-global dict is wiped
# whenever the user edits the plugin and Sublime reloads it, which would leave a
# focused window "orphaned": the next toggle would re-enter instead of exit and
# focus mode could never be turned off again. window.settings()/view.settings()
# live on the C++ side and survive plugin reloads, so they are the source of
# truth here.
WIN_ACTIVE_KEY = "focus_mode_window_active"
WIN_CHROME_KEY = "focus_mode_window_chrome"
WIN_FULLSCREEN_KEY = "focus_mode_window_fullscreen_toggled"
VIEW_SAVED_KEY = "focus_mode_window_saved"

VIEW_SETTING_KEYS = (
    "color_scheme",
    "draw_centered",
    "word_wrap",
    "wrap_width",
    "rulers",
    "gutter",
    "line_numbers",
    "margin",
    "line_padding_top",
    "line_padding_bottom",
    "font_size",
    "highlight_line",
    "scroll_past_end",
    "typewriter_mode_scrolling",
)

# (name, getter, setter) for the window chrome we toggle. Some of these methods
# do not exist on every Sublime Text build/platform, so each call is guarded
# with hasattr() at runtime. A single missing/raising API must never abort the
# whole enter/exit flow.
WINDOW_CHROME = (
    ("sidebar", "is_sidebar_visible", "set_sidebar_visible"),
    ("minimap", "is_minimap_visible", "set_minimap_visible"),
    ("tabs", "is_tabs_visible", "set_tabs_visible"),
    ("menu", "is_menu_visible", "set_menu_visible"),
    ("status_bar", "is_status_bar_visible", "set_status_bar_visible"),
)

# Window ids currently running their exit/restore sequence. While a window is
# in here the on_activated listener must NOT re-focus any view: erasing a view's
# VIEW_SAVED_KEY during exit could otherwise let the listener re-capture the
# already-focused settings as "original" and re-apply them, silently undoing the
# exit ("focus mode won't turn off").
_exiting_windows = set()


def _log(message):
    print("[FocusMode] " + message)


def plugin_loaded():
    _log("plugin loaded (module focus_mode_window). Command: toggle_focus_mode_window")


def plugin_unloaded():
    _log("plugin unloaded")


def _plugin_settings():
    return sublime.load_settings(SETTINGS_FILE)


def _window_settings(window):
    """Return the window-level Settings object, or None on builds without it."""
    if window is None or not hasattr(window, "settings"):
        return None
    try:
        return window.settings()
    except Exception:
        _log("error obtaining window.settings():\n" + traceback.format_exc())
        return None


def _is_focus_window(window):
    if window is None:
        return False
    ws = _window_settings(window)
    if ws is not None:
        return bool(ws.get(WIN_ACTIVE_KEY, False))
    # Fallback for builds without window.settings(): a window is "in focus" if
    # any of its views still carries saved (pre-focus) settings.
    for view in window.views():
        if view.settings().has(VIEW_SAVED_KEY):
            return True
    return False


def _safe_get_chrome(window, getter):
    """Read a window-chrome visibility flag, tolerating missing APIs."""
    if not hasattr(window, getter):
        _log("window has no %s(); skipping capture" % getter)
        return None
    try:
        return bool(getattr(window, getter)())
    except Exception:
        _log("error calling %s():\n%s" % (getter, traceback.format_exc()))
        return None


def _safe_set_chrome(window, setter, value):
    """Set a window-chrome visibility flag, tolerating missing APIs."""
    if value is None:
        return
    if not hasattr(window, setter):
        _log("window has no %s(); skipping apply" % setter)
        return
    try:
        getattr(window, setter)(value)
    except Exception:
        _log("error calling %s(%r):\n%s" % (setter, value, traceback.format_exc()))


def _capture_view_settings(view):
    settings = view.settings()
    return {
        key: {"has": settings.has(key), "value": settings.get(key)}
        for key in VIEW_SETTING_KEYS
    }


def _restore_view_settings(view):
    """Undo focus styling for a view by erasing every key the plugin set.

    Every key in VIEW_SETTING_KEYS is a view-local override added by this plugin
    on enter (``_focus_view`` captures+applies a view exactly once, guarded by
    VIEW_SAVED_KEY). Erasing them lets each setting fall back to the user's
    normal global / syntax / project layer, which is the only thing that
    reliably restores the original color scheme and re-enables Ctrl+wheel /
    Ctrl+-/= zoom (a re-pinned view-local ``font_size`` would mask global zoom).

    We intentionally do NOT ``set()`` captured values back: ``settings.has(key)``
    is True for keys that merely exist in a lower layer (e.g. global font_size),
    so re-setting them would pin a brand-new view-local override. Unconditional
    erase is the simple, correct choice. The only edge cost is that a genuine
    pre-existing per-view override is also cleared back to global (rare).
    """
    settings = view.settings()
    erased = []
    for key in VIEW_SETTING_KEYS:
        settings.erase(key)
        erased.append(key)
    return erased


def _apply_focus_to_view(view, plugin_settings):
    vs = view.settings()
    vs.set("color_scheme", plugin_settings.get("color_scheme", DEFAULT_COLOR_SCHEME))
    vs.set("highlight_line", True)
    vs.set("draw_centered", True)
    vs.set("word_wrap", True)
    vs.set("wrap_width", plugin_settings.get("wrap_width", 78))
    vs.set("rulers", [])
    vs.set("gutter", False)
    vs.set("line_numbers", False)
    vs.set("margin", plugin_settings.get("margin", 48))
    vs.set("line_padding_top", plugin_settings.get("line_padding_top", 8))
    vs.set("line_padding_bottom", plugin_settings.get("line_padding_bottom", 8))
    vs.set("scroll_past_end", True)
    vs.set("typewriter_mode_scrolling", True)
    # font_size is optional: set it to 0 (or null) in settings to keep your
    # normal font size while focused, leaving Ctrl+-/= zoom untouched.
    font_size = plugin_settings.get("font_size", 16)
    if font_size:
        vs.set("font_size", font_size)


def _focus_view(view, plugin_settings):
    """Capture a view's current settings and apply focus styling, once."""
    vs = view.settings()
    if vs.has(VIEW_SAVED_KEY):
        return False
    vs.set(VIEW_SAVED_KEY, _capture_view_settings(view))
    _apply_focus_to_view(view, plugin_settings)
    return True


def _unfocus_view(view):
    """Restore a view if it is currently in focus mode."""
    vs = view.settings()
    if not vs.has(VIEW_SAVED_KEY):
        return False
    erased = _restore_view_settings(view)
    vs.erase(VIEW_SAVED_KEY)
    _log("view %d erased=%s" % (view.id(), erased))
    return True


class ToggleFocusModeWindowCommand(sublime_plugin.WindowCommand):
    def run(self, force=None):
        active = _is_focus_window(self.window)
        _log("run(force=%r) active=%s window=%s" % (force, active, self.window.id()))
        if force is True and active:
            _log("already in focus mode; nothing to do")
            return
        if force is False and not active:
            _log("not in focus mode; nothing to do")
            return
        try:
            if active:
                self._exit_focus()
            else:
                self._enter_focus()
        except Exception:
            # Sublime swallows WindowCommand exceptions; surface them loudly so
            # "the command does nothing" is never a silent mystery again.
            _log("UNHANDLED ERROR in toggle:\n" + traceback.format_exc())
            sublime.status_message("Focus Mode Window: error (see console)")

    def is_checked(self, force=None):
        return _is_focus_window(self.window)

    def _enter_focus(self):
        window = self.window
        _log("entering focus mode")
        settings = _plugin_settings()
        ws = _window_settings(window)

        chrome = {}
        for name, getter, _setter in WINDOW_CHROME:
            chrome[name] = _safe_get_chrome(window, getter)

        if ws is not None:
            ws.set(WIN_CHROME_KEY, chrome)
            ws.set(WIN_ACTIVE_KEY, True)

        for name, _getter, setter in WINDOW_CHROME:
            _safe_set_chrome(window, setter, False)

        fullscreen_toggled = False
        if bool(settings.get("full_screen", False)):
            window.run_command("toggle_full_screen")
            fullscreen_toggled = True
        if ws is not None:
            ws.set(WIN_FULLSCREEN_KEY, fullscreen_toggled)

        styled = 0
        for view in window.views():
            if _focus_view(view, settings):
                styled += 1

        _log("focus mode ON (%d views styled)" % styled)
        sublime.status_message("Focus Mode Window: on")

    def _exit_focus(self):
        window = self.window
        _log("exiting focus mode")
        ws = _window_settings(window)

        # Read the snapshot first, then immediately mark the window as NOT in
        # focus (and as "exiting") BEFORE restoring any view. Doing this first
        # closes the on_activated re-entry race that otherwise undoes the exit.
        chrome = ws.get(WIN_CHROME_KEY, {}) if ws is not None else {}
        fullscreen_toggled = bool(ws.get(WIN_FULLSCREEN_KEY, False)) if ws is not None else False

        if ws is not None:
            ws.set(WIN_ACTIVE_KEY, False)
        _exiting_windows.add(window.id())
        try:
            for name, _getter, setter in WINDOW_CHROME:
                saved_value = chrome.get(name) if chrome else None
                # Fall back to "visible" when the original value is unknown.
                _safe_set_chrome(window, setter, True if saved_value is None else saved_value)

            if fullscreen_toggled:
                window.run_command("toggle_full_screen")

            restored = 0
            for view in list(window.views()):
                if _unfocus_view(view):
                    restored += 1

            if ws is not None:
                ws.erase(WIN_ACTIVE_KEY)
                ws.erase(WIN_CHROME_KEY)
                ws.erase(WIN_FULLSCREEN_KEY)
        finally:
            _exiting_windows.discard(window.id())

        _log("focus mode OFF (restored %d views)" % restored)
        sublime.status_message("Focus Mode Window: off")


class FocusModeWindowDiagnoseCommand(sublime_plugin.WindowCommand):
    def run(self):
        window = self.window
        ws = _window_settings(window)
        view = window.active_view()
        _log("---- diagnose (window %s) ----" % window.id())
        _log("is_focus_window=%s" % _is_focus_window(window))
        _log("window.settings() available=%s" % (ws is not None))
        if ws is not None:
            _log("WIN_ACTIVE_KEY=%r" % ws.get(WIN_ACTIVE_KEY, None))
            _log("WIN_CHROME_KEY=%r" % ws.get(WIN_CHROME_KEY, None))
        _log("exiting_in_progress=%s" % (window.id() in _exiting_windows))
        if view is None:
            _log("no active view")
        else:
            vs = view.settings()
            _log("active view %d:" % view.id())
            _log("  has %s=%s" % (VIEW_SAVED_KEY, vs.has(VIEW_SAVED_KEY)))
            for key in ("color_scheme", "highlight_line", "font_size",
                        "draw_centered", "word_wrap"):
                _log("  %s=%r" % (key, vs.get(key)))
        _log("---- end diagnose ----")
        sublime.status_message("Focus Mode Window: diagnose printed to console")


class FocusModeWindowListener(sublime_plugin.EventListener):
    def on_activated(self, view):
        window = view.window()
        if not _is_focus_window(window):
            return
        # Never re-focus while this window is tearing down focus mode, or the
        # exit would be silently undone (see _exiting_windows note above).
        if window is not None and window.id() in _exiting_windows:
            return
        if not view.settings().has(VIEW_SAVED_KEY):
            if _focus_view(view, _plugin_settings()):
                _log("styled newly activated view %d" % view.id())
