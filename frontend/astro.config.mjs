// @ts-check
import node from "@astrojs/node";
import preact from "@astrojs/preact";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig, envField } from "astro/config";
import path from "path";

import compressor from "astro-compressor";

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

  integrations: [preact(), compressor()],

  env: {
    schema: {
      ABR_INTERNAL__API_PORT: envField.number({
        context: "client",
        access: "public",
        default: 42456,
      }),
    },
  },

  output: "server",
  server: { port, host: true },

  adapter: node({
    mode: "standalone",
  }),
});
