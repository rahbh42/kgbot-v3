import React from "react";
import { createRoot } from "react-dom/client";

console.log("[BOOT] main.jsx loaded"); // <-- should appear even if App fails

async function start() {
  try {
    console.log("[BOOT] before importing App.jsx");
    const { default: App } = await import("./ui/App.jsx"); // <-- IMPORTANT: ./ui/App.jsx
    console.log("[BOOT] after importing App.jsx");
    const el = document.getElementById("root");
    if (!el) {
      console.error("[BOOT] #root not found in index.html");
      return;
    }
    createRoot(el).render(<App />);
    console.log("[BOOT] React render called");
  } catch (err) {
    console.error("[BOOT] FAILED to start app:", err);
    const el = document.getElementById("root");
    if (el) el.innerHTML = `<pre style="color:#a00;white-space:pre-wrap">Boot error: ${String(err)}</pre>`;
  }
}

start();
