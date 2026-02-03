/**
 * Adds user session information typing to Astro.locals
 */
/// <reference path="../.astro/types.d.ts" />
/// <reference types="astro/client" />
/// <reference types="@astrojs/image/client" />
declare namespace App {
  interface Locals {
    user: import("@/client").UserResponse | null;
  }
}
