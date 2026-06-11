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


def _restore_view_settings(view, saved):
    """Undo focus styling for a view.

    The key subtlety: ``view.settings().has(key)`` is True when the key exists
    at *any* layer (global Preferences, syntax-specific settings, project), not
    only as a view-local override. So a captured ``has=True`` does NOT mean the
    view itself had an override. If we naively ``set()`` such a value back we
    pin a brand-new view-local override that masks the global setting forever -
    that is exactly what broke ``Ctrl+-/=`` font zoom (font_size got pinned).

    Correct behavior: always ``erase()`` our override first (revealing the
    user's normal layered value), then only re-pin a value when it was a
    genuine local override - detected by the captured value differing from what
    the layered config resolves to once our override is gone.
    """
    settings = view.settings()
    restored = []
    erased = []
    for key in VIEW_SETTING_KEYS:
        item = saved.get(key)
        if not item:
            continue
        settings.erase(key)
        if not item.get("has"):
            erased.append(key)
            continue
        prior_value = item.get("value")
        resolved = settings.get(key) if settings.has(key) else None
        if prior_value != resolved:
            settings.set(key, prior_value)
            restored.append(key)
        else:
            erased.append(key)
    return restored, erased


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
    """Restore a view from its saved settings, if it has any."""
    vs = view.settings()
    saved = vs.get(VIEW_SAVED_KEY)
    if not saved:
        return False
    restored, erased = _restore_view_settings(view, saved)
    vs.erase(VIEW_SAVED_KEY)
    _log("view %d restored set=%s erased=%s" % (view.id(), restored, erased))
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

        chrome = ws.get(WIN_CHROME_KEY, {}) if ws is not None else {}
        fullscreen_toggled = bool(ws.get(WIN_FULLSCREEN_KEY, False)) if ws is not None else False

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

        _log("focus mode OFF (restored %d views)" % restored)
        sublime.status_message("Focus Mode Window: off")


class FocusModeWindowListener(sublime_plugin.EventListener):
    def on_activated(self, view):
        window = view.window()
        if not _is_focus_window(window):
            return
        if not view.settings().has(VIEW_SAVED_KEY):
            if _focus_view(view, _plugin_settings()):
                _log("styled newly activated view %d" % view.id())
