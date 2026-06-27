import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { isApiRequest } from "./api/workOrdersApi";
import { AuthProvider, TOKEN_KEY, USER_KEY } from "./context/AuthContext";
import "./styles.css";

// Global fetch interceptor — injects the Authorization header and handles 401s, but only for
// requests that target our own API (see isApiRequest). Scoping it this way keeps the Bearer token
// and the auth-expiry redirect from leaking to any third-party origin a fetch might hit.
const _originalFetch = window.fetch.bind(window);
window.fetch = async (input, init) => {
  const targetsApi = isApiRequest(input);
  const token = targetsApi ? localStorage.getItem(TOKEN_KEY) : null;
  const patchedInit: RequestInit = {
    ...init,
    headers: {
      ...init?.headers,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  };
  const response = await _originalFetch(input, patchedInit);
  if (targetsApi && response.status === 401 && window.location.pathname !== "/login") {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
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
