import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";

// `?mock=graph` renders the standalone process-graph mockup instead of the
// app, so the layout can be reviewed before it is wired to live job data.
// Lazily imported so the mock data stays out of the production bundle.
const ProcessGraph = lazy(() =>
  import("./ProcessGraph").then((module) => ({ default: module.ProcessGraph })),
);

const mock = new URLSearchParams(window.location.search).get("mock");

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {mock === "graph" ? (
      <Suspense fallback={null}>
        <ProcessGraph />
      </Suspense>
    ) : (
      <App />
    )}
  </StrictMode>,
);
