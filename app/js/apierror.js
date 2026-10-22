// ApiError lives in its own module so both the network backend (api.js) and the in-browser backend (offline.js)
// can throw it without importing each other. api.js re-exports it: `import { ApiError } from "./api.js"` still works.

/** `status` is the HTTP status when the server answered (409 = stale rev), else null. */
export class ApiError extends Error {
  constructor(message, status = null) {
    super(message);
    this.status = status;
  }
}
