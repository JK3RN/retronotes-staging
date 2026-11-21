"""User functions and commands must be updated here in the same change."""
FIELD_MANUAL = '''RETRO // NOTES 0.2 — FIELD MANUAL

FILE
Ctrl+N          NEW NOTE — title, Enter create, Esc cancel
                Empty title becomes Untitled.
Ctrl+P          NOTE INDEX — newest first, fuzzy filename search
Ctrl+S          SAVE / retry after a write error
Ctrl+W          SAVE AND CLOSE
F1              FIELD MANUAL
Esc             CLOSE OVERLAY / return to writing
Ctrl+Z          UNDO (native GTK)
Ctrl+Shift+Z    REDO (native GTK)

NOTE INDEX
Type            FILTER in search field
Down / Up       SELECT and focus the result list
Tab / Shift+Tab Move between search and results
Enter           OPEN selected note
R               RENAME when the result list has focus
                Edit title, Enter rename, Esc cancel.
D D             DELETE when the result list has focus
                Two separate D presses within 4 seconds confirm the same note.
                Holding D does not confirm.
                Esc, selection changes, or searching cancel confirmation.
                Files move to NOTES/.trash without overwriting.
                Restore manually with ordinary file tools.
                Trash is excluded from the index; no restore UI.
                In the search field R and D are ordinary letters.

SEARCH
Ctrl+F          FIND in current note
Enter           NEXT MATCH, wrapping at document end
Esc             Return to editor; selected match stays selected

QUICK CAPTURE / COMMANDS
rnote           Open newest note; on an empty index ask for a title
rnote --quick   Create a timestamped Capture and open the editor
Ctrl+Enter      SAVE AND CLOSE in Quick Capture
rnote "text"    Direct capture, no GTK/window; appends one newline
                Unicode and Markdown are preserved.
rnote --notes-dir PATH
                Override ~/Notes; default never depends on working directory
rnote --no-focus-line
                Disable subtle current-line background
rnote --no-glow  Disable experimental up to 60 ms fresh character brightness
rnote --smooth-caret
                Enable experimental 55 ms visual caret movement for A/B tests.
                Native cursor remains the default.
                Selection, IME, overwrite and split bidi carets use native paint.
                Large jumps, pointer placement and viewport changes snap.
                System reduced-motion settings keep the native caret.
rnote --version Print version
rnote --help    Show CLI usage
./rnote         Local checkout entry point, same options
python install.py [--prefix PATH]
                Install under ~/.local by default, no root access.
                Symlink targets inside the prefix are rejected.
python install.py --uninstall [--prefix PATH]
                Remove installed program; notes are preserved
                Add PREFIX/bin to PATH if needed.

WRITING / STORAGE
Plain UTF-8 Markdown, one .md file per note.
Names: YYYY-MM-DD_HHMMSS__Readable-Title.md; collisions get --2, --3, ...
Unicode letters/digits are retained; unsafe characters become hyphens.
Rename preserves the timestamp; legacy files use their modification date.
New notes use mode 0600. New notes folders and Trash use mode 0700.
Only regular .md files are indexed and opened. Note symlinks are ignored.
Invalid UTF-8 or embedded NUL bytes cause an open error.
Choose a notes directory controlled by your own user.
Autosave after 500 ms pause and before switching or closing.
MODIFIED / SAVED / ERROR states appear at the bottom.
Write failure or external-change conflict prevents closing/switching.
For a conflict copy your unsaved text and merge files externally.
No locking for simultaneous writers. Use one editor per file.

MARKDOWN / PHOSPHOR
Headings, list/quote markers, **bold**, and `inline code` use live text tags.
Syntax remains editable. This is not a complete Markdown parser.
TODO: IDEA: NOTE: FIX: — accent
WARN: — warning / critical color; DONE: — completed accent
Native input and scrolling; optional visual-only smooth caret, no text trails.
Experimental fresh character brightness expires within 60 ms.
Focus Line is a very subtle current-line background.

THEME
System palette: XDG_STATE_HOME then XDG_CONFIG_HOME,
 omarchy/current/theme/colors.toml
Defaults: ~/.local/state and ~/.config.
Existing theme directories are watched, including symlink replacement.
Missing/invalid palette: dark phosphor green with amber accents.
Omamji works when it supplies those shared palette paths.
No desktop settings are changed.
'''
