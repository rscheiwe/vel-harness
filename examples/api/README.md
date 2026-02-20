# FastAPI Examples

Each file is a standalone FastAPI app serving vel-harness as a chat API.

## Setup

```bash
pip install -e ".[dev]"
pip install fastapi uvicorn python-dotenv

# Set your API key
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
```

## Examples

| File | Port | What it covers |
|---|---|---|
| `basic_chat.py` | 8000 | Minimal SSE streaming + sync endpoint |
| `sessions_and_models.py` | 8001 | Persistent sessions, model hot-switching, reasoning modes, interrupt |
| `tools_hooks_approval.py` | 8002 | Custom tools, pre/post hooks (block/modify/audit), tool approval REST flow |
| `skills_and_subagents.py` | 8003 | Skill loading/creation, custom agent types, subagent spawning |
| `advanced_features.py` | 8004 | Caching, retry, fallback model, checkpoints/rewind, memory, database |
| `websocket_chat.py` | 8005 | WebSocket bidirectional chat with real-time approval |
| `full_chat_app.py` | 8080 | Everything combined — production-like app |

## Running

```bash
# Pick one:
uvicorn examples.api.basic_chat:app --reload --port 8000
uvicorn examples.api.full_chat_app:app --reload --port 8080
uvicorn examples.api.websocket_chat:app --reload --port 8005
```

## Feature coverage

```
VelHarness init params        Covered in
─────────────────────         ──────────
model                         all
tools (custom)                tools_hooks_approval, websocket_chat, full_chat_app
skill_dirs                    skills_and_subagents, full_chat_app
custom_agents                 skills_and_subagents, websocket_chat, full_chat_app
system_prompt                 (omitted — overriding breaks caching)
max_turns                     (uses default 100)
working_directory             skills_and_subagents, advanced_features, full_chat_app
sandbox                       all
database                      advanced_features
planning                      all
memory                        advanced_features, websocket_chat, full_chat_app
caching                       advanced_features, websocket_chat, full_chat_app
retry                         advanced_features, websocket_chat, full_chat_app
hooks                         tools_hooks_approval, full_chat_app
reasoning                     sessions_and_models
fallback_model                advanced_features, websocket_chat, full_chat_app
max_fallback_retries          advanced_features, full_chat_app
tool_approval_callback        tools_hooks_approval

HarnessSession methods        Covered in
──────────────────────        ──────────
query() (streaming)           sessions_and_models, advanced_features, websocket_chat, full_chat_app
run() (sync)                  sessions_and_models, full_chat_app
set_model()                   sessions_and_models, websocket_chat, full_chat_app
set_reasoning()               sessions_and_models, websocket_chat, full_chat_app
interrupt()                   sessions_and_models, websocket_chat, full_chat_app
create_checkpoint()           advanced_features, full_chat_app
rewind_files()                advanced_features, full_chat_app
get_changed_files()           advanced_features, full_chat_app
get_state()                   sessions_and_models, advanced_features, full_chat_app

Other features                Covered in
──────────────────────        ──────────
ApprovalManager               tools_hooks_approval, full_chat_app
HookEngine (pre/post)         tools_hooks_approval, full_chat_app
AgentDefinition               skills_and_subagents, websocket_chat, full_chat_app
register_agent()              skills_and_subagents, websocket_chat, full_chat_app
Skill (runtime creation)      skills_and_subagents
get_state() (harness-level)   advanced_features, full_chat_app
FallbackStreamWrapper         advanced_features, websocket_chat, full_chat_app
FileCheckpointManager         advanced_features, full_chat_app
```
