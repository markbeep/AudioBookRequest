export const regions = [
  "us",
  "ca",
  "uk",
  "au",
  "fr",
  "de",
  "jp",
  "it",
  "in",
  "es",
  "br",
] as const;

export type Region = (typeof regions)[number];
