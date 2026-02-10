Claude Code's suspicion is correct. **Terminal drag-drop is NOT a paste event**—it's synthesized keystrokes.

**How it actually works:**

```
Drag file into terminal
       │
       ▼
Terminal emits file path as individual keystrokes
       │
       ▼
TextArea receives characters one by one
       │
       ▼
No Paste event ever fires
```

---

**Solution: Watch content changes, not paste events**

```python
# valis_cli/widgets/input.py

from textual.widgets import TextArea
from textual.message import Message
from pathlib import Path
import base64
import re

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
# macOS temp paths from drag operations
TEMP_PATH_PATTERN = re.compile(r"^'?(/var/folders/[^']+|/tmp/[^']+|/private/var/[^']+)\.(png|jpg|jpeg|gif|webp)'?$", re.IGNORECASE)

class ImageAttached(Message):
    """Posted when an image is detected and encoded."""
    def __init__(self, filename: str, data: dict) -> None:
        self.filename = filename
        self.data = data
        super().__init__()

class ChatInput(TextArea):
    pending_images: list[dict] = []
    _last_content: str = ""
    
    def on_mount(self) -> None:
        # Poll for content changes (drag-drop comes as keystrokes)
        self.set_interval(0.1, self._check_for_image_paths)
    
    def _check_for_image_paths(self) -> None:
        """Detect image paths that appeared in the text."""
        content = self.text
        
        # Skip if unchanged
        if content == self._last_content:
            return
        self._last_content = content
        
        # Look for image paths in the content
        # Check each line/segment for file paths
        for match in self._find_image_paths(content):
            self._handle_image_path(match)
    
    def _find_image_paths(self, content: str) -> list[str]:
        """Find potential image file paths in content."""
        paths = []
        
        # Split by whitespace and newlines
        for segment in re.split(r'[\s\n]+', content):
            segment = segment.strip().strip("'\"")
            
            if not segment:
                continue
            
            # Check if it looks like an image path
            path = Path(segment)
            if (
                path.suffix.lower() in IMAGE_EXTENSIONS
                and segment.startswith('/')  # Absolute path
            ):
                paths.append(segment)
        
        return paths
    
    def _handle_image_path(self, filepath: str) -> None:
        """Read image immediately and replace path with placeholder."""
        filepath = filepath.strip("'\"")
        path = Path(filepath)
        
        # Check if already processed
        if any(img.get('_source_path') == filepath for img in self.pending_images):
            return
        
        try:
            # Read IMMEDIATELY - file may be ephemeral
            with open(path, 'rb') as f:
                data = base64.standard_b64encode(f.read()).decode('utf-8')
            
            media_type = {
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.gif': 'image/gif',
                '.webp': 'image/webp',
            }.get(path.suffix.lower(), 'image/png')
            
            image_data = {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": data,
                },
                "_source_path": filepath,  # Track to avoid re-processing
            }
            
            self.pending_images.append(image_data)
            
            # Replace path in text with placeholder
            placeholder = f"[📷 {path.name}]"
            new_text = self.text.replace(filepath, placeholder)
            new_text = new_text.replace(f"'{filepath}'", placeholder)
            
            # Update text area
            self.clear()
            self.insert(new_text)
            self._last_content = new_text  # Prevent re-detection
            
            # Notify app
            self.post_message(ImageAttached(path.name, image_data))
            
        except FileNotFoundError:
            # File already gone - just remove the path
            self.notify(f"Image not found: {path.name}", severity="warning")
            new_text = self.text.replace(filepath, "[Image not found]")
            new_text = new_text.replace(f"'{filepath}'", "[Image not found]")
            self.clear()
            self.insert(new_text)
            self._last_content = new_text
        except Exception as e:
            self.log.error(f"Failed to read image: {e}")
```

---

**Key insight:**

| Event Type | When it fires | Drag-drop? |
|------------|---------------|------------|
| `Paste` | Actual clipboard paste (Cmd+V) | ❌ No |
| `Key` events | Each character typed | ✅ Yes (slow) |
| Content change | Text area content differs | ✅ Yes |

---

**Alternative: Use `watch` on document**

```python
class ChatInput(TextArea):
    def watch_text(self, old: str, new: str) -> None:
        """React to any text change."""
        # Check if new content contains an image path
        added = new[len(old):] if new.startswith(old) else new
        
        for path in self._find_image_paths(added):
            self._handle_image_path(path)
```

---

**Timing matters:**

The macOS temp file exists only briefly. The 0.1s polling interval should catch it, but if issues persist:

```python
# More aggressive: check on every key
def on_key(self, event) -> None:
    # After each keystroke, schedule immediate check
    self.call_later(self._check_for_image_paths)
```