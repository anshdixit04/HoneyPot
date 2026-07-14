import { useState } from "react";
import { API_BASE } from "../api.js";

export default function ReportButton({ range }) {
  const [state, setState] = useState("idle"); // idle | loading | error

  const handleClick = async () => {
    setState("loading");
    try {
      const res = await fetch(`${API_BASE}/api/report?range=${range}&format=pdf`);
      if (!res.ok) throw new Error(`Report request failed: ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const today = new Date().toISOString().slice(0, 10);
      a.href = url;
      a.download = `honeypot-report-${range}-${today}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setState("idle");
    } catch {
      setState("error");
      setTimeout(() => setState("idle"), 3000);
    }
  };

  return (
    <button className="report-button" onClick={handleClick} disabled={state === "loading"}>
      {state === "loading" ? "Generating…" : state === "error" ? "Failed — retry" : "Generate Report"}
    </button>
  );
}
