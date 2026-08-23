import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { ProcessGraph } from "./ProcessGraph";
import "./styles.css";

// `?mock=graph` renders the standalone process-graph mockup instead of the
// app, so the layout can be reviewed before it is wired to live job data.
const mock = new URLSearchParams(window.location.search).get("mock");

createRoot(document.getElementById("root")!).render(
  <StrictMode>{mock === "graph" ? <ProcessGraph /> : <App />}</StrictMode>,
);
