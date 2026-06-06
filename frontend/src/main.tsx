import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { AuthProvider } from "./context/AuthContext";
import "./styles.css";

// Global fetch interceptor — injects Authorization header and handles 401
const _originalFetch = window.fetch.bind(window);
window.fetch = async (input, init) => {
  const token = localStorage.getItem("auth_token");
  const patchedInit: RequestInit = {
    ...init,
    headers: {
      ...init?.headers,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  };
  const response = await _originalFetch(input, patchedInit);
  if (response.status === 401 && window.location.pathname !== "/login") {
    localStorage.removeItem("auth_token");
    localStorage.removeItem("auth_user");
    window.location.href = "/login";
  }
  return response;
};

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
