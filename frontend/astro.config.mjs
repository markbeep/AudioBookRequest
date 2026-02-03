// @ts-check
import path from "path";
import { defineConfig, envField } from "astro/config";
import tailwindcss from "@tailwindcss/vite";
import preact from "@astrojs/preact";

import node from "@astrojs/node";

let port = 8000;
try {
  const value = process.env.ABR_APP__PORT;
  if (!value) {
    port = 8000;
  } else if (isNaN(parseInt(value))) {
    throw new Error("Invalid port number");
  } else {
    port = parseInt(value);
  }
} catch {
  console.error(
    "Invalid port number in ABR_APP__PORT environment variable. Using default port 8000.",
  );
}

// https://astro.build/config
export default defineConfig({
  vite: {
    plugins: [tailwindcss()],
    resolve: {
      alias: {
        "@": path.resolve("./src"),
      },
    },
  },

  integrations: [preact()],

  env: {
    schema: {
      ABR_INTERNAL__API_PORT: envField.number({
        context: "client",
        access: "public",
        default: 8000,
      }),
    },
  },

  output: "server",
  server: { port, host: true },

  adapter: node({
    mode: "standalone"
  })
});