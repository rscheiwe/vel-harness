That's input handling in the CLI, not the model. Rough implementation:

```python
# In the input widget / paste handler

PASTE_COLLAPSE_THRESHOLD = 20  # lines

def handle_paste(self, text: str) -> None:
    lines = text.split('\n')
    
    if len(lines) > PASTE_COLLAPSE_THRESHOLD:
        # Store full text for actual submission
        self.pending_paste = text
        
        # Display collapsed preview
        preview = f"[Pasted {len(lines)} lines]"
        self.display_collapsed_paste(preview)
    else:
        # Short paste, show inline
        self.insert_text(text)

def on_submit(self) -> None:
    # Expand collapsed paste when sending
    if self.pending_paste:
        message = self.pending_paste
        self.pending_paste = None
    else:
        message = self.input_text
    
    self.send_message(message)
```

---

**UX details:**

| Behavior | Implementation |
|----------|----------------|
| Collapse threshold | ~20 lines |
| Display | `[Pasted 247 lines]` (clickable to expand?) |
| Expand on hover/click | Show full content in modal or inline |
| Submit | Always sends full content to API |

---

**For Valis CLI** (Textual-based), you'd add this to the input widget:

```python
# valis_cli/widgets/input.py

class ChatInput(TextArea):
    pending_paste: str | None = None
    
    def _on_paste(self, event: Paste) -> None:
        lines = event.text.split('\n')
        
        if len(lines) > 10:
            self.pending_paste = event.text
            self.insert(f"[Pasted {len(lines)} lines]")
            event.prevent_default()
        # else: default paste behavior
```