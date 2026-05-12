# Telegram + FastAPI + Windows Agent Design

Date: 2026-05-12
Status: Draft approved in chat, written for review

## 1. Context

The current repository is a copied snapshot of a larger local computer-use agent project. It already contains working pieces for:

- local agent loop execution;
- Windows computer control tools;
- Telegram interaction;
- interrupt handling;
- memory and usage tracking;
- watchdog-based process recovery.

In its current form, the repository is not a clean study project. It looks like a monolithic local prototype where Telegram, agent logic, and computer control are tightly coupled.

The target state is a study project that clearly demonstrates separation between frontend and backend, while preserving the main functional idea: a user can send a task remotely and a local client can manipulate the user's Windows PC.

## 2. Goal

Build a cleaned-up educational project with explicit distributed architecture:

- Telegram Bot as the user-facing frontend;
- FastAPI as the cloud backend and system orchestrator;
- a local Windows client as the execution agent on the user's PC.

The project must remain single-user and single-PC. It should preserve the current computer-control functionality and the agentic execution model, but present them inside a cleaner architecture suitable for demonstration, explanation, and grading.

## 3. Success Criteria

The project is successful if:

- a reviewer can immediately identify separate frontend, backend, and local client parts in the repository structure;
- the backend is deployed outside the local PC and acts as the center of system state;
- the Telegram bot works only as a frontend and does not directly control the PC;
- the local Windows client performs real computer manipulation using the existing agent/tooling approach;
- the complete end-to-end flow works: Telegram message -> backend task -> local client execution -> result back to Telegram;
- the repository is cleaned from unrelated historical files and looks intentionally designed for the study assignment.

## 4. Non-Goals

The following are explicitly out of scope for the minimum study version:

- multi-user support;
- multiple clients or device fleet management;
- a web frontend such as Streamlit;
- external production database infrastructure;
- complex authentication and account management;
- making the system a full SaaS product;
- preserving all historical documentation and release artifacts from the source repository.

## 5. Target Architecture

The system consists of three separate applications.

### 5.1 Telegram Bot Frontend

The Telegram bot is the user interface of the system.

Responsibilities:

- receive tasks from the user;
- show progress updates;
- show screenshots and textual intermediate output;
- show final results and failure messages;
- expose service commands such as `/start`, `/reset`, and `/stats`.

The bot must not contain the core execution logic for computer control. It only forwards user intent to the backend and renders backend state back to the user.

### 5.2 Cloud Backend on FastAPI

The FastAPI service is the central backend and source of truth.

Responsibilities:

- accept user requests from the Telegram bot;
- create and track tasks;
- store task state, execution events, interrupts, memory, and usage statistics;
- provide polling endpoints for the local client;
- receive execution updates, screenshots, and final results from the local client;
- provide data needed by the Telegram bot to inform the user.

The backend does not click, type, or take screenshots itself. Its role is orchestration and persistence.

### 5.3 Local Windows Agent Client

The local client runs on the user's Windows machine.

Responsibilities:

- periodically poll the backend for new work;
- execute tasks locally using the existing agent loop and computer-use tools;
- collect screenshots, intermediate tool output, and final results;
- send step events and completion status back to the backend;
- support interrupt handling based on new user messages stored on the backend;
- continue to use watchdog-style recovery for resilience.

This client is the only component allowed to directly manipulate the Windows desktop.

## 6. Responsibility Boundaries

The architectural boundary must stay explicit:

- frontend = Telegram user interaction;
- backend = task lifecycle, state, persistence, coordination;
- client = local execution on the PC.

This separation is essential for the educational value of the project. It must be obvious both in the code and in the repository layout.

## 7. High-Level Flow

1. The user sends a task to the Telegram bot.
2. The bot forwards the message to the FastAPI backend.
3. The backend creates a new task with status `pending`.
4. The local Windows client polls the backend and receives the active task.
5. The client starts the current agent loop and performs local actions on the PC.
6. The client sends intermediate events to the backend, including text updates, tool outputs, screenshots, and status changes.
7. The backend stores these events and exposes them to the Telegram bot.
8. The bot relays useful updates to the user.
9. If the user sends another message while execution is in progress, the bot forwards it to the backend as an interrupt for the active task.
10. The client receives the interrupt on the next poll cycle and injects it into the running agent flow.
11. When the task completes or fails, the client posts the final result to the backend.
12. The backend marks the task as `done` or `failed`, and the bot shows the final outcome to the user.

## 8. MVP Functional Scope

The educational MVP keeps the main functionality of the current project, but re-homes it inside the new architecture.

Required functionality:

- Telegram task submission;
- backend task creation and queueing;
- polling-based client task retrieval;
- local agentic execution on Windows;
- screenshots and text progress updates;
- interrupt handling from new Telegram messages;
- memory persistence;
- usage statistics;
- `/reset` and `/stats`;
- watchdog for the local client.

Not required for MVP:

- multi-user sessions;
- multiple simultaneous active tasks;
- websocket transport;
- browser UI;
- advanced deployment automation.

## 9. Data and State Model

The backend owns the canonical state.

At minimum, the system should model:

- `ClientStatus`: online/offline, last heartbeat, current task id;
- `Task`: id, original user message, status, created time, updated time;
- `TaskEvent`: text update, screenshot, tool output, warning, internal event;
- `Interrupt`: task id, text, created time, consumed flag;
- `UsageStats`: token counters and cost-related aggregates;
- `MemoryState`: structured memory reused by the agent across tasks.

The backend remains the canonical owner of persisted task state, interrupts, memory snapshots, and usage aggregates. The client may keep short-lived local runtime state while executing a task, but long-term state should be pushed back to the backend.

For the educational version, persistence can be implemented with SQLite or a compact JSON-based storage layer. SQLite is preferred because it looks cleaner on review while staying simple.

## 10. Failure Handling

The system must fail gracefully.

- If the client is offline, tasks remain pending on the backend.
- If the client stops sending heartbeat signals, the backend marks it offline.
- If the agent loop crashes, the local watchdog restarts the client process.
- If Telegram delivery temporarily fails, task state is still preserved on the backend.
- If a task fails during execution, the final backend state must still reflect `failed` plus error details.

The minimum system only needs to support one user, one active client, and one active task at a time. This simplification is intentional and acceptable for the assignment.

## 11. Repository Restructuring Plan

The cleaned repository should make the architecture visually obvious.

Target structure:

```text
/
├── backend/
├── bot/
├── client/
├── shared/
├── tests/
├── docs/
│   ├── architecture.md
│   ├── deployment.md
│   └── superpowers/
│       └── specs/
├── README.md
└── requirements.txt
```

### 11.1 Code to Keep

The following current areas are likely to be reused inside `client/`:

- agent loop logic;
- Windows computer tools;
- interrupt mechanics;
- local memory-building and fact-extraction logic, adapted so canonical persistence lives on the backend;
- local usage collection, adapted so aggregates are reported to the backend;
- watchdog behavior.

### 11.2 Code to Move or Rewrite

The following logic must be separated out of the current monolithic shape:

- Telegram handling must move into `bot/`;
- state coordination must move into `backend/`;
- shared request/response schemas must move into `shared/`;
- local execution wiring must stay in `client/` and stop talking to Telegram directly.

### 11.3 Files to Remove During Cleanup

The cleanup phase should delete or archive:

- release notes from the previous project;
- upgrade guides from the previous project;
- changelog content unrelated to the study version;
- research-heavy or historical docs not needed for the new architecture;
- any legacy entry points that imply the bot and execution engine are one application.

## 12. Testing Strategy

The minimum acceptable test coverage should focus on architectural behavior.

Required tests:

- backend task creation and status transition tests;
- backend polling and interrupt handling tests;
- schema validation tests for shared models;
- client-side tests for memory and interrupt integration where feasible;
- at least one integration scenario that covers:
  Telegram message -> backend task -> client poll -> result update.

Manual demo scenario for review:

1. User sends a task in Telegram.
2. Backend records the task.
3. Local client picks it up and manipulates the PC.
4. User sees progress and final result in Telegram.
5. User interrupts a task and the agent changes course.

## 13. Why This Design Fits the Assignment

This design is suitable for the study assignment because:

- it shows explicit frontend/backend separation;
- part of the code lives in the cloud as required;
- the local client is a distinct application with its own role;
- the project still demonstrates a technically interesting real-world feature: remote computer control through an LLM-driven agent;
- the repository can be made much cleaner than the copied source project while preserving the strongest functional idea.

## 14. Open Implementation Direction

The next phase should produce an implementation plan that:

- identifies which current files move into `client/` with minimal rewriting;
- defines backend API endpoints for tasks, events, interrupts, and heartbeats;
- defines Telegram bot behavior as a thin frontend adapter;
- plans the repo cleanup in safe, reviewable stages.

This design intentionally chooses the architecture that best balances:

- clear educational separation;
- reuse of existing working functionality;
- manageable implementation effort.
