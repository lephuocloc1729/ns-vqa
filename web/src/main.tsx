import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/newsreader"; // the brand name's serif, bundled (no external font request)
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
