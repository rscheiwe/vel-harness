"""
Chat Input Widget

Input field for user messages with history and slash command support.
Supports multi-line input with Shift+Enter for newlines and Enter to submit.
Supports image paste/drag-drop via file path detection.
"""

import base64
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# macOS pasteboard support for drag-drop images
try:
    from AppKit import NSPasteboard, NSPasteboardTypePNG, NSPasteboardTypeTIFF
    HAS_APPKIT = True
except ImportError:
    HAS_APPKIT = False

# File system watcher for capturing temp files before they disappear
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False


class TempImageCache:
    """Cache for images captured by file watcher before they disappear."""

    _instance = None
    _cache: Dict[str, Dict[str, Any]] = {}  # path -> {data, media_type, timestamp}
    _observer = None
    _watching = False

    @classmethod
    def get_instance(cls) -> 'TempImageCache':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def start_watching(self) -> None:
        """Start watching temp directories for new image files."""
        if not HAS_WATCHDOG or self._watching:
            return

        import threading
        import time

        class ImageFileHandler(FileSystemEventHandler):
            def __init__(self, cache: 'TempImageCache'):
                self.cache = cache

            def on_created(self, event):
                if event.is_directory:
                    return
                path = event.src_path
                # Debug log ALL file creations
                with open("/tmp/valis_watchdog_debug.log", "a") as f:
                    f.write(f"[CREATED] {path}\n")
                # Check if it's an image file
                suffix = Path(path).suffix.lower()
                if suffix in IMAGE_EXTENSIONS:
                    with open("/tmp/valis_watchdog_debug.log", "a") as f:
                        f.write(f"[IMAGE] Attempting to read: {path}\n")
                    # Read IMMEDIATELY - file may be ephemeral
                    try:
                        with open(path, 'rb') as f:
                            data = base64.standard_b64encode(f.read()).decode('utf-8')
                        media_type = MIME_TYPES.get(suffix, 'image/png')
                        self.cache._cache[path] = {
                            'data': data,
                            'media_type': media_type,
                            'timestamp': time.time(),
                            'filename': Path(path).name,
                        }
                        with open("/tmp/valis_watchdog_debug.log", "a") as f:
                            f.write(f"[SUCCESS] Cached {len(data)} bytes for {path}\n")
                    except Exception as e:
                        with open("/tmp/valis_watchdog_debug.log", "a") as f:
                            f.write(f"[FAILED] {path}: {e}\n")

        self._observer = Observer()
        handler = ImageFileHandler(self)

        # Watch macOS temp directories
        temp_dirs = [
            '/var/folders/',  # macOS temp
            '/tmp/',
            os.path.expanduser('~/Library/Caches/'),
        ]

        with open("/tmp/valis_watchdog_debug.log", "a") as f:
            f.write(f"[STARTUP] Starting watchdog observer\n")

        for temp_dir in temp_dirs:
            if os.path.exists(temp_dir):
                try:
                    self._observer.schedule(handler, temp_dir, recursive=True)
                    with open("/tmp/valis_watchdog_debug.log", "a") as f:
                        f.write(f"[WATCHING] {temp_dir}\n")
                except Exception as e:
                    with open("/tmp/valis_watchdog_debug.log", "a") as f:
                        f.write(f"[ERROR] Failed to watch {temp_dir}: {e}\n")

        self._observer.start()
        self._watching = True
        with open("/tmp/valis_watchdog_debug.log", "a") as f:
            f.write(f"[STARTED] Observer running\n")

        # Clean old entries periodically
        def cleanup():
            while self._watching:
                time.sleep(60)
                cutoff = time.time() - 300  # 5 min
                self._cache = {k: v for k, v in self._cache.items()
                              if v['timestamp'] > cutoff}

        cleanup_thread = threading.Thread(target=cleanup, daemon=True)
        cleanup_thread.start()

    def stop_watching(self) -> None:
        """Stop the file watcher."""
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=1)
        self._watching = False

    def get(self, path: str) -> Optional[Dict[str, Any]]:
        """Get cached image data for a path."""
        # Try exact match
        if path in self._cache:
            return self._cache[path]
        # Try with path normalization
        normalized = str(Path(path).resolve()) if path else None
        if normalized and normalized in self._cache:
            return self._cache[normalized]
        # Try matching by filename (in case paths differ slightly)
        filename = Path(path).name if path else None
        if filename:
            for cached_path, data in self._cache.items():
                if data.get('filename') == filename:
                    return data
        return None

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.events import Key, Paste
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Static, TextArea


# Supported image extensions
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}

# MIME type mapping
MIME_TYPES = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.bmp': 'image/bmp',
}


class ChatTextArea(TextArea):
    """Custom TextArea: Enter submits, backslash+Enter continues to new line.

    Detects image file paths via content watching (not paste events).
    Terminal drag-drop emits keystrokes, not paste events.
    """

    class Submitted(Message):
        """Fired when Enter is pressed."""

        def __init__(self, value: str, pending_paste: Optional[str] = None):
            self.value = value
            self.pending_paste = pending_paste
            super().__init__()

    class ImageDetected(Message):
        """Fired when an image file path is detected and encoded."""

        def __init__(self, filepath: str, filename: str, media_type: str, data: str):
            self.filepath = filepath
            self.filename = filename
            self.media_type = media_type
            self.data = data  # base64 encoded
            super().__init__()

    PASTE_COLLAPSE_THRESHOLD = 10  # Lines before collapsing

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._placeholder = kwargs.get("placeholder", "")
        self._last_text = ""
        self._processed_paths: set = set()  # Track already-processed paths
        self._pending_paste: Optional[str] = None  # Full content of collapsed paste

    def on_paste(self, event: Paste) -> None:
        """Handle paste - collapse long text into placeholder."""
        if not event.text:
            return

        lines = event.text.split('\n')
        char_count = len(event.text)

        # Collapse if many lines OR very long text
        if len(lines) > self.PASTE_COLLAPSE_THRESHOLD or char_count > 500:
            # Store full text for submission
            self._pending_paste = event.text
            # Insert collapsed placeholder
            if len(lines) > 1:
                self.insert(f"[Pasted {len(lines)} lines]")
            else:
                self.insert(f"[Pasted {char_count} chars]")
            event.prevent_default()
            event.stop()
        # Short paste - let normal paste proceed

    def on_mount(self) -> None:
        """Start polling for image paths (drag-drop comes as keystrokes)."""
        # Start the temp image watcher (captures files at creation time)
        TempImageCache.get_instance().start_watching()
        # Backup polling in case other methods miss something
        self.set_interval(0.02, self._check_for_image_paths)

    def _on_text_area_changed(self, event) -> None:
        """React immediately to any text change."""
        self._check_for_image_paths()

    def _check_for_image_paths(self) -> None:
        """Detect image paths that appeared in the text."""
        content = self.text

        # Skip if unchanged
        if content == self._last_text:
            return

        # Clean up orphan quotes after replacement (from drag-drop timing)
        if self._last_text.endswith(']') and content == self._last_text + "'":
            self.clear()
            self.insert(self._last_text)
            return

        self._last_text = content

        # Look for image paths in the content
        for filepath in self._find_image_paths(content):
            if filepath not in self._processed_paths:
                self._handle_image_path(filepath)

    def _find_image_paths(self, content: str) -> List[str]:
        """Find potential image file paths in content."""
        paths = []

        # First: look for quoted paths (handles spaces in filenames)
        # Match 'path' or "path" where path ends with image extension
        quoted_pattern = r"['\"]([^'\"]+\.(?:png|jpg|jpeg|gif|webp|bmp))['\"]"
        for match in re.finditer(quoted_pattern, content, re.IGNORECASE):
            path_str = match.group(1)
            if path_str.startswith('/') or path_str.startswith('~'):
                paths.append(path_str)

        # Second: look for INCOMPLETE quoted paths (file may exist before quote closes)
        # Match opening quote + path ending with image extension (no closing quote yet)
        if not paths:
            incomplete_pattern = r"['\"]([^'\"]+\.(?:png|jpg|jpeg|gif|webp|bmp))$"
            for match in re.finditer(incomplete_pattern, content, re.IGNORECASE):
                path_str = match.group(1)
                if path_str.startswith('/') or path_str.startswith('~'):
                    paths.append(path_str)

        # Third: look for unquoted absolute paths (no spaces)
        if not paths:
            for segment in re.split(r'[\s\n]+', content):
                segment = segment.strip()
                if not segment:
                    continue
                if segment.startswith('/') or segment.startswith('~'):
                    try:
                        path = Path(segment).expanduser()
                        if path.suffix.lower() in IMAGE_EXTENSIONS:
                            paths.append(segment)
                    except (OSError, ValueError, RuntimeError):
                        pass

        return paths

    def _read_from_pasteboard(self) -> Optional[tuple]:
        """Try to read image data from macOS pasteboard.

        Returns (data_bytes, media_type) or None if no image available.
        """
        if not HAS_APPKIT:
            return None

        try:
            from AppKit import NSBitmapImageRep, NSPNGFileType, NSURL

            pb = NSPasteboard.generalPasteboard()

            # Debug: log available types
            types = pb.types()
            with open("/tmp/valis_pasteboard_debug.log", "a") as f:
                f.write(f"Pasteboard types: {list(types) if types else 'None'}\n")

            # Try PNG first
            png_data = pb.dataForType_(NSPasteboardTypePNG)
            if png_data:
                return (bytes(png_data), 'image/png')

            # Try TIFF (common for screenshots)
            tiff_data = pb.dataForType_(NSPasteboardTypeTIFF)
            if tiff_data:
                try:
                    rep = NSBitmapImageRep.imageRepWithData_(tiff_data)
                    if rep:
                        png_data = rep.representationUsingType_properties_(NSPNGFileType, None)
                        if png_data:
                            return (bytes(png_data), 'image/png')
                except Exception:
                    return (bytes(tiff_data), 'image/tiff')

            # Try file URL (when file is copied in Finder)
            file_url_data = pb.dataForType_("public.file-url")
            if file_url_data:
                url_str = file_url_data.bytes().tobytes().decode('utf-8').rstrip('\x00')
                with open("/tmp/valis_pasteboard_debug.log", "a") as f:
                    f.write(f"File URL: {url_str}\n")
                if url_str.startswith("file://"):
                    from urllib.parse import unquote
                    filepath = unquote(url_str[7:])  # Remove file:// prefix
                    path = Path(filepath)
                    if path.suffix.lower() in IMAGE_EXTENSIONS and path.exists():
                        with open(path, 'rb') as f:
                            data = f.read()
                        media_type = MIME_TYPES.get(path.suffix.lower(), 'image/png')
                        return (data, media_type)

            return None
        except Exception as e:
            with open("/tmp/valis_pasteboard_debug.log", "a") as f:
                f.write(f"Pasteboard error: {e}\n")
            return None

    def _handle_image_path(self, filepath: str) -> None:
        """Read image immediately and replace path with placeholder."""
        filepath_clean = filepath.strip("'\"")
        path = Path(filepath_clean).expanduser()
        name = path.name

        data = None
        media_type = None

        # Try watchdog cache FIRST (file captured at creation time)
        cache = TempImageCache.get_instance()
        cached = cache.get(str(path))
        if cached:
            data = cached['data']
            media_type = cached['media_type']

        # Try reading file directly
        if not data:
            try:
                with open(path, 'rb') as f:
                    data = base64.standard_b64encode(f.read()).decode('utf-8')
                media_type = MIME_TYPES.get(path.suffix.lower(), 'image/png')
            except FileNotFoundError:
                pass  # Will try pasteboard next
            except PermissionError:
                self._processed_paths.add(filepath)
                self.notify("Cannot read image (permission denied)", severity="error")
                return
            except Exception as e:
                self._processed_paths.add(filepath)
                self.notify(f"Failed to read image: {e}", severity="error")
                return

        # Try pasteboard as last resort
        if not data:
            pb_result = self._read_from_pasteboard()
            if pb_result:
                raw_data, media_type = pb_result
                data = base64.standard_b64encode(raw_data).decode('utf-8')

        # Mark as processed (all quote variants)
        self._processed_paths.add(filepath)
        self._processed_paths.add(filepath_clean)
        self._processed_paths.add(f"'{filepath_clean}'")
        self._processed_paths.add(f'"{filepath_clean}"')

        if data:
            # Success - emit message
            self.post_message(self.ImageDetected(
                filepath=str(path),
                filename=name,
                media_type=media_type,
                data=data,
            ))
            placeholder = f"[{name}]"
        else:
            # No data from file or pasteboard
            self.notify(f"Image not found: {name}", severity="warning")
            placeholder = "[Image not found]"

        # Replace path in text with placeholder
        new_text = self.text
        new_text = new_text.replace(f"'{filepath_clean}'", placeholder)
        new_text = new_text.replace(f'"{filepath_clean}"', placeholder)
        new_text = new_text.replace(filepath_clean, placeholder)

        self.clear()
        self.insert(new_text)
        self._last_text = new_text

    async def _on_key(self, event: Key) -> None:
        """Handle key events - Enter submits, backslash+Enter continues."""
        # Check for image paths after each keystroke (drag-drop = fast keystrokes)
        self.call_later(self._check_for_image_paths)

        if event.key == "enter":
            # Check if line ends with backslash (continuation)
            text = self.text
            cursor_row, cursor_col = self.cursor_location

            # Get text up to cursor on current line
            lines = text.split("\n")
            if cursor_row < len(lines):
                current_line = lines[cursor_row][:cursor_col]
                if current_line.endswith("\\"):
                    # Remove the backslash and insert newline
                    event.prevent_default()
                    event.stop()
                    # Delete the backslash then insert newline
                    self.action_delete_left()
                    self.insert("\n")
                    return

            # No backslash - submit
            event.prevent_default()
            event.stop()
            pending = self._pending_paste
            self._pending_paste = None
            self.post_message(self.Submitted(self.text, pending_paste=pending))
            return

        # Default handling for all other keys
        await super()._on_key(event)


class ChatInput(Widget):
    """Input widget for chat messages with multi-line support."""

    DEFAULT_CSS = """
    ChatInput {
        height: auto;
        dock: bottom;
        padding: 0 1;
        background: $surface;
    }

    ChatInput Horizontal {
        height: auto;
        padding: 1 0;
    }

    ChatInput ChatTextArea {
        width: 1fr;
        height: auto;
        min-height: 3;
        max-height: 10;
        border: tall $primary-darken-2;
    }

    ChatInput ChatTextArea:focus {
        border: tall $primary;
    }

    ChatInput Button {
        width: auto;
        min-width: 6;
        margin-left: 1;
    }

    ChatInput .prompt {
        width: auto;
        padding: 1 1 1 0;
        color: $primary;
        text-style: bold;
    }

    ChatInput .image-indicator {
        display: none;
    }
    """

    BINDINGS = [
        Binding("escape", "clear", "Clear", show=False),
        Binding("ctrl+v", "paste_with_image", "Paste", show=False),
        Binding("cmd+v", "paste_with_image", "Paste", show=False),
    ]

    class Submitted(Message):
        """Message sent when input is submitted."""

        def __init__(self, value: str, images: Optional[List[Dict[str, Any]]] = None):
            self.value = value
            self.images = images or []
            super().__init__()

    class SlashCommand(Message):
        """Message sent when a slash command is entered."""

        def __init__(self, command: str, args: List[str]):
            self.command = command
            self.args = args
            super().__init__()

    class PasteImage(Message):
        """Message sent when /paste captures an image from clipboard."""

        def __init__(self, data: str, media_type: str, filename: str):
            self.data = data
            self.media_type = media_type
            self.filename = filename
            super().__init__()

    def __init__(
        self,
        placeholder: str = "Enter message...",
        prompt: str = "> ",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.placeholder = placeholder
        self.prompt = prompt
        self._history: List[str] = []
        self._history_index: int = -1
        self._temp_input: str = ""
        self._pending_images: List[Dict[str, Any]] = []
        self._pending_paste: Optional[str] = None  # Collapsed paste content
        self.PASTE_COLLAPSE_THRESHOLD = 10  # Lines before collapsing

    def compose(self) -> ComposeResult:
        """Compose the input widget."""
        with Horizontal():
            yield Static(self.prompt, classes="prompt")
            yield Static("", id="image-indicator", classes="image-indicator")
            yield ChatTextArea(id="chat-input")
            yield Button("Send", id="send-btn", variant="primary")

    def on_mount(self) -> None:
        """Handle mount event."""
        self.query_one("#chat-input", ChatTextArea).focus()

    def on_paste(self, event) -> None:
        """Handle paste - check for image or long text."""
        # Debug
        with open("/tmp/valis_paste_debug.log", "a") as f:
            f.write(f"[PASTE] lines={len(event.text.split(chr(10))) if event.text else 0}\n")

        # Always check clipboard for image first
        image_data = self._read_clipboard_image()
        if image_data:
            data, media_type = image_data
            self._pending_images.append({
                "type": "image",
                "image": data,
                "mimeType": media_type,
                "_filename": "clipboard.png",
            })
            # Insert placeholder in text area
            input_widget = self.query_one("#chat-input", ChatTextArea)
            input_widget.insert("[clipboard.png] ")
            event.prevent_default()
            event.stop()
            return

        # Check for long text paste - collapse if over threshold
        if event.text:
            lines = event.text.split('\n')
            char_count = len(event.text)

            # Debug
            with open("/tmp/valis_paste_debug.log", "a") as f:
                f.write(f"[PASTE DETAIL] lines={len(lines)}, chars={char_count}\n")

            # Collapse if many lines OR very long text
            if len(lines) > self.PASTE_COLLAPSE_THRESHOLD or char_count > 500:
                # Store full text for submission
                self._pending_paste = event.text
                # Insert collapsed placeholder
                input_widget = self.query_one("#chat-input", ChatTextArea)
                if len(lines) > 1:
                    input_widget.insert(f"[Pasted {len(lines)} lines] ")
                else:
                    input_widget.insert(f"[Pasted {char_count} chars] ")
                event.prevent_default()
                event.stop()
                return
        # Short paste - let normal paste proceed

    def on_key(self, event) -> None:
        """Handle key events - check for paste shortcut."""
        # Check for paste shortcuts
        if event.key in ("ctrl+v", "ctrl+shift+v"):
            image_data = self._read_clipboard_image()
            if image_data:
                data, media_type = image_data
                self._pending_images.append({
                    "type": "image",
                    "image": data,
                    "mimeType": media_type,
                    "_filename": "clipboard.png",
                })
                # Insert placeholder in text area
                input_widget = self.query_one("#chat-input", ChatTextArea)
                input_widget.insert("[clipboard.png] ")
                event.prevent_default()
                event.stop()
                return

    def on_chat_text_area_image_detected(self, event: ChatTextArea.ImageDetected) -> None:
        """Handle image detection from text area content watching."""
        # Store image data for submission
        self._pending_images.append({
            "type": "image",
            "image": event.data,
            "mimeType": event.media_type,
            "_filename": event.filename,  # For display only
        })
        # Update indicator
        self._update_image_indicator()

    def _read_clipboard_image(self) -> Optional[tuple]:
        """Read image data from macOS clipboard.

        Returns (base64_data, media_type) or None.
        """
        if not HAS_APPKIT:
            return None

        try:
            from AppKit import NSBitmapImageRep, NSPNGFileType

            pb = NSPasteboard.generalPasteboard()

            # Try PNG
            png_data = pb.dataForType_(NSPasteboardTypePNG)
            if png_data:
                data = base64.standard_b64encode(bytes(png_data)).decode('utf-8')
                return (data, 'image/png')

            # Try TIFF (screenshots)
            tiff_data = pb.dataForType_(NSPasteboardTypeTIFF)
            if tiff_data:
                # Convert TIFF to PNG
                rep = NSBitmapImageRep.imageRepWithData_(tiff_data)
                if rep:
                    png_data = rep.representationUsingType_properties_(NSPNGFileType, None)
                    if png_data:
                        data = base64.standard_b64encode(bytes(png_data)).decode('utf-8')
                        return (data, 'image/png')

            # Try file URL
            file_url_data = pb.dataForType_("public.file-url")
            if file_url_data:
                from urllib.parse import unquote
                url_str = bytes(file_url_data).decode('utf-8').rstrip('\x00')
                if url_str.startswith("file://"):
                    filepath = unquote(url_str[7:])
                    path = Path(filepath)
                    if path.suffix.lower() in IMAGE_EXTENSIONS and path.exists():
                        with open(path, 'rb') as f:
                            data = base64.standard_b64encode(f.read()).decode('utf-8')
                        media_type = MIME_TYPES.get(path.suffix.lower(), 'image/png')
                        return (data, media_type)

            return None
        except Exception as e:
            return None

    def _update_image_indicator(self) -> None:
        """Update the image indicator display."""
        indicator = self.query_one("#image-indicator", Static)
        count = len(self._pending_images)
        if count == 0:
            indicator.update("")
        elif count == 1:
            name = self._pending_images[0].get("_filename", "image")
            indicator.update(f"[{name}]")
        else:
            indicator.update(f"[{count} images]")

    def on_chat_text_area_submitted(self, event: ChatTextArea.Submitted) -> None:
        """Handle text area submission (Enter key)."""
        # Use pending paste from ChatTextArea if present
        if event.pending_paste:
            self._pending_paste = event.pending_paste
        self._submit(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "send-btn":
            input_widget = self.query_one("#chat-input", ChatTextArea)
            # Get pending paste from ChatTextArea
            if input_widget._pending_paste:
                self._pending_paste = input_widget._pending_paste
                input_widget._pending_paste = None
            self._submit(input_widget.text)

    def _submit(self, value: str) -> None:
        """Submit the input value."""
        value = value.strip()

        # Expand collapsed paste if present
        if self._pending_paste:
            # Replace the placeholder with actual content
            import re
            # Find and replace placeholder (can't use re.sub because replacement may have backslashes)
            match = re.search(r'\[Pasted \d+ (?:lines|chars)\]', value)
            if match:
                value = value[:match.start()] + self._pending_paste + value[match.end():]
            else:
                # No placeholder found, just prepend the paste
                value = self._pending_paste + " " + value
            self._pending_paste = None

        # Allow submission with just images (no text)
        if not value and not self._pending_images:
            return

        # Add to history (display version, not expanded)
        display_value = value[:100] + "..." if len(value) > 100 else value
        if display_value and (not self._history or self._history[-1] != display_value):
            self._history.append(display_value)
        self._history_index = -1

        # Clear input
        input_widget = self.query_one("#chat-input", ChatTextArea)
        input_widget.clear()

        # Check for slash commands (only if no images attached)
        if value.startswith("/") and not self._pending_images:
            parts = value[1:].split()
            if parts:
                cmd = parts[0].lower()

                # Handle /paste command - read image from clipboard
                if cmd == "paste":
                    image_data = self._read_clipboard_image()
                    if image_data:
                        data, media_type = image_data
                        self._pending_images.append({
                            "type": "image",
                            "image": data,
                            "mimeType": media_type,
                            "_filename": "clipboard.png",
                        })
                        self._update_image_indicator()
                        self.notify("Image captured from clipboard")
                        # Don't return - allow user to add text after /paste
                        # Or submit with just the image
                        if len(parts) > 1:
                            # Text after /paste
                            value = " ".join(parts[1:])
                        else:
                            # Just /paste - submit with image only
                            images = self._pending_images.copy()
                            self._pending_images = []
                            self._update_image_indicator()
                            self.post_message(self.Submitted("", images=images))
                            return
                    else:
                        self.notify("No image found in clipboard", severity="warning")
                        return

                self.post_message(self.SlashCommand(parts[0], parts[1:]))
                return

        # Get pending images and clear them
        images = self._pending_images.copy()
        self._pending_images = []
        self._update_image_indicator()

        # Regular message (with optional images)
        self.post_message(self.Submitted(value, images=images))

    def action_paste_with_image(self) -> None:
        """Handle Ctrl+V - check for image in clipboard first."""
        # Try to get image from clipboard
        image_data = self._read_clipboard_image()
        if image_data:
            data, media_type = image_data
            self._pending_images.append({
                "type": "image",
                "image": data,
                "mimeType": media_type,
                "_filename": "clipboard.png",
            })
            self._update_image_indicator()
            self.notify("Image pasted from clipboard")
            return

        # No image - try to paste text from clipboard
        if HAS_APPKIT:
            pb = NSPasteboard.generalPasteboard()
            text = pb.stringForType_("public.utf8-plain-text")
            if text:
                input_widget = self.query_one("#chat-input", ChatTextArea)
                input_widget.insert(text)

    def action_clear(self) -> None:
        """Clear the input and pending content."""
        input_widget = self.query_one("#chat-input", ChatTextArea)
        input_widget.clear()
        input_widget._pending_paste = None
        self._history_index = -1
        self._pending_images = []
        self._pending_paste = None
        self._update_image_indicator()

    def focus_input(self) -> None:
        """Focus the input field."""
        self.query_one("#chat-input", ChatTextArea).focus()

    def set_value(self, value: str) -> None:
        """Set the input value."""
        input_widget = self.query_one("#chat-input", ChatTextArea)
        input_widget.clear()
        input_widget.insert(value)

    def get_value(self) -> str:
        """Get the current input value."""
        return self.query_one("#chat-input", ChatTextArea).text

    def disable(self) -> None:
        """Disable input."""
        self.query_one("#chat-input", ChatTextArea).disabled = True
        self.query_one("#send-btn", Button).disabled = True

    def enable(self) -> None:
        """Enable input."""
        self.query_one("#chat-input", ChatTextArea).disabled = False
        self.query_one("#send-btn", Button).disabled = False
        self.focus_input()


class MultiLineInput(Widget):
    """Multi-line input widget for longer messages."""

    DEFAULT_CSS = """
    MultiLineInput {
        height: auto;
        min-height: 3;
        max-height: 10;
        dock: bottom;
        padding: 0 1;
        border: solid $primary;
    }

    MultiLineInput TextArea {
        height: auto;
        min-height: 1;
    }
    """

    class Submitted(Message):
        """Message sent when input is submitted."""

        def __init__(self, value: str):
            self.value = value
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        from textual.widgets import TextArea
        yield TextArea(id="multi-input")

    def get_value(self) -> str:
        """Get the current value."""
        from textual.widgets import TextArea
        return self.query_one("#multi-input", TextArea).text

    def clear(self) -> None:
        """Clear the input."""
        from textual.widgets import TextArea
        self.query_one("#multi-input", TextArea).clear()
