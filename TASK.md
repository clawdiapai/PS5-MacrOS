# 🏛️ Web2PS5: Architecture Brief & Build Protocol

<system_directive>
You are acting as a Senior Systems Architect and Hardware Automation Engineer. 
We are building **Web2PS5**: a high-speed, ComfyUI-style visual automation studio for the PlayStation 5.

This document outlines the current vision, proposed architecture, and draft node ecosystem. 
**Your first task is NOT to write the application code.**
Your first task is to evaluate this architecture. We will undergo a couple of rounds of planning. You must highlight potential bottlenecks, concurrency issues, or UI/UX hurdles in the proposed stack, and propose alternative directions if you deem them superior. 
Once we finalize the plan, we will build incrementally using a strictly documented, resumable process.
</system_directive>

## 1. The Core Vision
We are abandoning a traditional sequential-step web app in favor of a **Visual Node Graph** using `litegraph.js` (the same underlying engine as ComfyUI). 
*   **The Frontend** is purely a visualizer and authoring tool. 
*   **The Backend** (Python) is the execution engine, maintaining the hardware locks, reading the video frames, and walking the graph state.

## 2. Proposed Architecture (For Your Evaluation)
Please review the following proposed subsystem boundaries and advise if this is the optimal path:

*   **API & Sockets:** FastAPI + Uvicorn on `asyncio`. WebSocket broadcasts for live node telemetry (making the active node "glow" on the canvas).
*   **Video Ingest:** A background thread decoding the PS5 H.264 stream and placing *only the most recent frame* into an `AtomicFrameHolder` (size=1 ring buffer) to guarantee OpenCV always analyzes the present moment, zero lag.
*   **Graph VM (The Runner):** An async Token Interpreter running in Python. It parses the LiteGraph JSON, maintains a Context Scope for variable passing, and walks the `EXEC` pins. It must yield `await asyncio.sleep(0)` during vision polling to keep the web server alive.
*   **Hardware Bridge:** Remote Play UDP packets wrapped in an `asyncio.Lock()`. UDP requires holding a button state for a minimum duration (e.g., 80ms) followed by an explicit release frame to prevent dropped inputs.

*Question for Grok: Does this async/threading split between FastAPI, OpenCV, and UDP seem robust? Are there better patterns for managing the Token VM state?*

## 3. Draft Node Ecosystem
This graph requires a mix of Execution nodes (Event/Action driven) and Data nodes. Please review this list and suggest refinements or missing logic.

### 🎮 DualSense (Hardware Inputs)
*   `ds.press` / `ds.hold` / `ds.stick`: Standard controller inputs.
*   `ds.delay`: Pauses the execution token.
*   `ds.macro_block`: A node with a "Record" button in the UI. It listens to a physical PC-connected gamepad, records the UDP timings, and plays them back when triggered.

### 👁️ Vision (Action & Logic)
*   `vis.wait_anchor`: Pauses execution until a specific template matches the live screen. Outputs `EXEC_FOUND` or `EXEC_TIMEOUT`.
*   `vis.check_state`: Instant template match. Outputs a `BOOL` and a `FLOAT` (confidence score).
*   `vis.move_focus`: Auto-seeker. Pulses a D-pad direction until a target icon gains the PS5's UI highlight glow.
*   `vis.screenshot_runtime`: Captures the current PS5 frame during graph execution and saves it to disk.

### 🖼️ Vision (Data / Authoring Time)
*These nodes act as static data providers for the canvas. They require custom LiteGraph UI widgets.*
*   `vis.anchor_studio`: Fetches the live MJPEG frame into the node. The user draws a box on the image to crop a template, saving it as an Anchor ID. (Outputs `STRING`).
*   `vis.define_roi`: Fetches a live frame. The user draws a box to define a Region of Interest. (Outputs `VEC4` bounding box to feed into `vis.wait_anchor` to optimize OpenCV processing).

### ⚡ Logic (Control Flow & State)
*   `logic.start`: Graph entry point.
*   `logic.branch`: If/Else router.
*   `logic.gates`: `AND`, `OR`, `NOT` nodes for combining boolean outputs from vision checks.
*   `logic.variables`: `set_var` and `get_var` to store state (e.g., "boss_defeated = True") across the graph lifecycle.
*   `logic.subgraph`: Executes a previously saved graph as a single node.

### 🔌 System (Webhooks & Power)
*   `sys.webhook`: Posts a payload (and optional screenshot) to Discord/Telegram.
*   `pwr.session`: Connects, disconnects, or pushes the PS5 to Rest Mode.

## 4. Build Protocol & Resumability

Once planning is complete, we will build this system in phases. To ensure this context is never lost if our chat session ends, we will adhere to the **State Tracker Protocol**:

1.  **Iterative Steps:** You will build one subsystem at a time (e.g., "Step 1: FastAPI + LiteGraph Shell"). Do not move to Step 2 until the user validates Step 1.
2.  **`BUILD_STATE.md`:** At the end of every major output, you must generate or update a `BUILD_STATE.md` block. This block will contain the current phase, completed tasks, pending tasks, and any architectural decisions made. 
3.  **Resumption:** If a new chat session is started, the user will paste the `BUILD_STATE.md` file, and you will instantly know exactly where we left off and what the next exact code requirement is.

<next_action>
Acknowledge these instructions. Provide your high-level architectural evaluation of Section 2 and Section 3. Do you see any risks in this ComfyUI/Python/UDP hybrid? Propose your feedback and outline what Phase 1 of our build should look like.
</next_action>