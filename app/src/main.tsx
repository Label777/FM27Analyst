import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import Compact from "./Compact";
import "./styles.css";

// Одно приложение — два окна: ?view=compact — виджет поверх игры, иначе — расширенная панель
const view = new URLSearchParams(window.location.search).get("view");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>{view === "compact" ? <Compact /> : <App />}</React.StrictMode>,
);
