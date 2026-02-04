import path from "path";

export function base(relative_path: string): string {
  return path.join(import.meta.env.BASE_URL, relative_path);
}
