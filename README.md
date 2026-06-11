# Focus Mode Window

A distraction-free **"focus mode"** plugin for [Sublime Text 4](https://www.sublimetext.com/).

Toggling focus mode hides all chrome (sidebar, minimap, tabs, menu, status bar)
and re-styles every open view with a centered, soft-wrapped, dimmed color scheme.
Only the **current line** stands out — everything else is pressed down close to
the background so your eye stays on what you're typing. Exiting restores every
setting exactly as it was.

## Features

- One command toggles the whole window in and out of focus mode.
- Hides sidebar, minimap, tabs, menu and status bar; optional OS full screen.
- Centered text column with configurable width, margins and line padding.
- Bundled `Focus Mode Window` color scheme that fades all syntax tokens and
  highlights only the active line.
- All original view/window settings are captured on entry and restored on exit.
- Newly opened/activated views inherit focus styling while focus mode is active.

## Installation

### Manual (Git clone)

Clone (or copy) this folder into your Sublime Text `Packages` directory so the
final path is `Packages/FocusModeWindow/`:

- **Windows:** `%APPDATA%\Sublime Text\Packages\FocusModeWindow`
- **macOS:** `~/Library/Application Support/Sublime Text/Packages/FocusModeWindow`
- **Linux:** `~/.config/sublime-text/Packages/FocusModeWindow`

You can open the right place from Sublime via **Preferences → Browse Packages…**

Restart Sublime Text after installing.

### Package Control

This package is structured for [Package Control](https://packagecontrol.io/).
Once published you can install it via **Command Palette
(`Ctrl+Shift+P`) → Package Control: Install Package → Focus Mode Window**.

Until then, add this repository as a custom source:
**Package Control: Add Repository** →
`https://github.com/codernull/FocusModeWindow`, then install as above.

> **Note:** the loadable Python plugin file is `focus_mode_window.py` (no
> spaces). The `Focus Mode Window.*` resource files (settings, commands, color
> scheme, keymap) keep spaces on purpose — Sublime resolves those by name.

## Usage

| Action | How |
| --- | --- |
| Toggle focus mode | Press `Shift+F11` |
| Toggle / Enter / Exit | Command Palette (`Ctrl+Shift+P`) → type `Focus Mode Window` |
| From the console | `window.run_command("toggle_focus_mode_window")` |

The same command can be forced on or off with an argument:

```py
window.run_command("toggle_focus_mode_window", {"force": True})   # enter
window.run_command("toggle_focus_mode_window", {"force": False})  # exit
```

## Configuration

Open **Preferences → Package Settings → Focus Mode Window**:

- **Settings – Default** — the bundled defaults (read for reference).
- **Settings – User** — your overrides (this file wins).
- **Color Scheme** — edit the dimming / current-line colors directly.
- **Key Bindings – Default / User** — view or remap the shortcut.

### Settings

| Key | Default | Meaning |
| --- | --- | --- |
| `color_scheme` | `Focus Mode Window.sublime-color-scheme` | Scheme used while focused |
| `wrap_width` | `78` | Soft-wrap column |
| `margin` | `48` | Horizontal margin of the centered column |
| `line_padding_top` | `8` | Pixels above each line |
| `line_padding_bottom` | `8` | Pixels below each line |
| `font_size` | `16` | Font size while focused (restored on exit) |
| `full_screen` | `false` | Also enter OS full screen |

### Colors (faded text & current-line highlight)

The bundled `Focus Mode Window` color scheme adapts the palette of
[**Focus** by Sindre Sorhus](https://github.com/sindresorhus/focus) (MIT): a
calm, warm-neutral dark background where syntax tokens are pressed down toward
the background so code reads as one quiet block, while prose, strings and
headings stay readable. The current line is marked by a soft, natural highlight
band — never a harsh colored bar.

Edit **Color Scheme** from the menu. Everything is driven by `variables` at the
top, so tweaking is easy:

- `dim` — how faded the non-prose text is (closer to `background` = more faded).
- `bright` — color of the text that should stand out (prose / strings).
- `line_highlight` — the band behind the current line (keep it close to
  `background` for a gentle effect).

## Troubleshooting

The plugin logs every step to the Sublime console. Open it with
**View → Show Console** (`` Ctrl+` ``) and look for `[FocusMode]` lines:

- On startup you should see
  `[FocusMode] plugin loaded (module focus_mode_window). ...`.
  **If this line is missing, the plugin did not load** — check that the folder
  is `Packages/FocusModeWindow/` and that `FocusModeWindow` is not listed in
  `ignored_packages` (Preferences → Settings).
- Each toggle prints `run(force=...) active=...` followed by
  `entering focus mode` / `exiting focus mode` and a final
  `focus mode ON (N views styled)` / `focus mode OFF (restored N views)` line.
  If exiting prints `restored 0 views` while you have files open, the state was
  lost — re-toggle once to re-sync.
- If a Sublime window API is missing on your build, you'll see a
  `window has no <method>(); skipping` line instead of a crash — the rest of
  focus mode still applies.
- Any unexpected error prints `UNHANDLED ERROR in toggle:` with a full
  traceback and shows `Focus Mode Window: error (see console)` in the status
  bar.

To force a reload after editing, save `focus_mode_window.py` or run
**Package Control: Satisfy Dependencies**, or just restart Sublime Text.

## Acknowledgements

The bundled color scheme adapts the palette of
[Focus](https://github.com/sindresorhus/focus) by Sindre Sorhus (MIT).

## License

[MIT](LICENSE) — do whatever you like.
