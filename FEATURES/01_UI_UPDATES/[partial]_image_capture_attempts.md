# Image Capture Attempts

## Goal
Allow users to drag/drop or paste images into Valis CLI chat input.

## Working Solution

### `/paste` Command
**Status:** WORKING

1. Take screenshot to clipboard: **Cmd+Ctrl+Shift+4** → select area
2. Type `/paste` in Valis CLI
3. Image is captured from clipboard and sent to LLM

```python
# In ChatInput._submit():
if cmd == "paste":
    image_data = self._read_clipboard_image()  # Uses pyobjc NSPasteboard
    if image_data:
        self._pending_images.append(...)
```

---

## The Problem (Drag-Drop)

Terminal drag-drop converts file paths to synthesized keystrokes. macOS temp files are deleted before keystrokes finish:

```
Drag starts → Temp file created → Keystrokes begin → ... → Keystrokes end → File deleted
                     │                                              │
                     └──── FILE EXISTS DURING THIS WINDOW ──────────┘
```

## Attempts

### 1. Paste Event Handler
**Status:** FAILED

```python
def on_paste(self, event: Paste) -> None:
    # Intercept paste, read file immediately
```

**Result:** Paste event never fires. Terminal drag-drop sends keystrokes, not paste events.

### 2. Content Watching (Polling)
**Status:** PARTIAL - detects path but file already gone

```python
def on_mount(self) -> None:
    self.set_interval(0.02, self._check_for_image_paths)
```

**Result:** Detection works (shows `[Image not found]`), but file deleted before we can read it.

### 3. PyObjC Pasteboard
**Status:** FAILED for drag-drop

```python
from AppKit import NSPasteboard, NSPasteboardTypePNG
pb = NSPasteboard.generalPasteboard()
png_data = pb.dataForType_(NSPasteboardTypePNG)
```

**Result:** Pasteboard only contains `public.utf8-plain-text` (the path), not image data.

### 4. textual-filedrop
**Status:** INCOMPATIBLE

```bash
pip install textual-filedrop
```

**Result:** Requires textual 0.15, vel-harness needs 0.47+.

---

## Untested Options

### 5. Clipboard Workflows (Manual)
**Status:** UNTESTED

**Option A: Screenshot to clipboard**
```
Cmd+Ctrl+Shift+4 → Cmd+V
```

**Option B: Copy file in Finder**
```
Select file → Cmd+C → Cmd+V in terminal
```

These should put actual image data or file URLs on the pasteboard.

### 6. Watchdog (File System Watcher)
**Status:** IMPLEMENTED - TESTING

```python
class TempImageCache:
    """Singleton cache that watches temp directories."""

    def start_watching(self):
        # Watches /var/folders/, /tmp/, ~/Library/Caches/
        # On file creation: read immediately, cache base64 data

    def get(self, path) -> Optional[Dict]:
        # Returns cached {data, media_type, filename} if available
```

**Advantage:** Captures file at creation time, before keystrokes even begin.

**Lookup order:**
1. Watchdog cache (captured at file creation)
2. Direct file read (if file still exists)
3. Pasteboard (clipboard fallback)

### 7. Trigger on Extension (Not Closing Quote)
**Status:** UNTESTED

```python
def watch_text(self, old: str, new: str) -> None:
    # Don't wait for full path - trigger on extension
    for ext in ['.png', '.jpg']:
        if ext in new.lower() and '/var/folders/' in new:
            match = re.search(r"'?(/var/folders/[^']*?" + ext + ")", new)
            if match:
                self._try_read_immediately(match.group(1))
```

### 8. iTerm2 File Transfer Protocol
**Status:** UNTESTED

iTerm2 supports OSC 1337 for file transfers:
```python
if os.environ.get('ITERM_SESSION_ID'):
    # Could use iTerm2's protocol
```

### 9. Poll During Keystroke Entry
**Status:** UNTESTED

```python
def on_key(self, event) -> None:
    text = self.text
    if '/var/folders/' in text and '/TemporaryItems/' in text:
        for match in re.finditer(r'/var/folders/[^\s\'\"]+\.png', text):
            path = match.group(0)
            if path not in self._attempted_paths:
                self._attempted_paths.add(path)
                self._try_read_immediately(path)
```

---

## Summary

| Method | Status | Notes |
|--------|--------|-------|
| `/paste` command | **WORKING** | Screenshot to clipboard → `/paste` |
| Drag-drop temp files | FAILED | File deleted in microseconds |
| Watchdog file watcher | FAILED | Event arrives after file deleted |
| Paste event (Cmd+V) | FAILED | Terminal sends text, not image |
| Pasteboard during drag | FAILED | Only contains path string |

## Current Implementation

File: `valis_cli/widgets/input.py`

**Working:**
- `/paste` command reads from NSPasteboard (PNG, TIFF, file URLs)

**Partial (for permanent files):**
- Content watching with polling (0.02s)
- Quoted path detection (handles spaces)
- Watchdog file watcher (caches on creation)
- Placeholder replacement on detection

## User Instructions

```
# To add an image:
1. Cmd+Ctrl+Shift+4 (screenshot to clipboard)
2. Select the area you want to capture
3. Type: /paste
4. Add optional text after the image
```
