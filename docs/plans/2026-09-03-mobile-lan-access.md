# Mobile LAN Access Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let the dashboard render comfortably on a phone and be reached from a phone on the same trusted Wi-Fi network.

**Architecture:** Keep the desktop sidebar at medium breakpoints and above. Below that, replace it with a sticky compact header and an overlay navigation drawer. Keep the backend loopback-only by default; opt in to LAN binding with an explicit environment variable and an explicit allowed-host list for mutating requests.

**Tech Stack:** React 19, Tailwind CSS, FastAPI/Uvicorn.

---

### Task 1: Add safe LAN binding configuration

**Files:**
- Modify: `server.py`
- Test: Python syntax compilation

1. Add a validated `VIBE_HOST` setting with a loopback-only default.
2. Bind Uvicorn to that setting and print the active address.
3. Document the environment variables in the README.
4. Compile the backend to verify syntax.

### Task 2: Add a phone navigation shell

**Files:**
- Modify: `frontend/src/components/layout/Layout.tsx`
- Test: `npm run build`, visual inspection at a phone viewport

1. Preserve the existing desktop sidebar from the `md` breakpoint upward.
2. Add a sticky phone header and accessible menu button below `md`.
3. Add an overlay navigation drawer that closes on route selection or outside click.
4. Reduce small-screen page gutters while retaining the desktop content width.
5. Build the frontend and visually check the dashboard at a phone viewport.
