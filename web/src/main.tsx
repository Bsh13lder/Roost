import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { installStaleBuildReload } from "./lib/staleBuild";
import { applyAccent, readAccent } from "./lib/accent";
// Type is the system stack (styles/tokens.css --font-sans, redesign P1): no font files ship.
import "./styles.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element (#root) not found in index.html");
}

// A tab open across an update reloads once to pick up the new build (lib/staleBuild.ts).
installStaleBuildReload(window, () => window.location.reload(), window.sessionStorage);

// The accent colour this browser remembers (Settings), applied before the first paint.
applyAccent(readAccent());

createRoot(rootElement).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
