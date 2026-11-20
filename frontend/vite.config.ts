import { createLogger, defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const proxy = { "/api": "http://127.0.0.1:8000" };

const logger = createLogger();
const logError = logger.error.bind(logger);
logger.error = (message, options) => {
  if (/\b(?:http|ws) proxy (?:socket )?error:/.test(message)) {
    logError("DataSleuth API proxy request failed.", { timestamp: true });
    return;
  }
  logError(message, options);
};

export default defineConfig({
  customLogger: logger,
  plugins: [react()],
  server: { host: "127.0.0.1", port: 5173, strictPort: true, proxy },
  preview: { host: "127.0.0.1", port: 5173, strictPort: true, proxy },
});
