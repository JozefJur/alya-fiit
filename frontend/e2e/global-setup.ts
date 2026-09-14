/**
 * Resets and seeds the dedicated E2E database before the suite runs, so every
 * run starts from the same known state (seed-small).
 */

import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

export default function globalSetup(): void {
  const repoRoot = path.resolve(import.meta.dirname, "..", "..");
  const backendDir = path.join(repoRoot, "backend");
  const venvPython = path.join(
    backendDir,
    ".venv",
    process.platform === "win32" ? "Scripts" : "bin",
    process.platform === "win32" ? "python.exe" : "python"
  );
  const python = existsSync(venvPython) ? venvPython : "python3";
  const e2eDatabase = path.join(backendDir, "data", "e2e.db");

  // manage.py empties the database in place, so a backend that already has the
  // file open keeps seeing the freshly seeded data.
  const result = spawnSync(
    python,
    [path.join("scripts", "manage.py"), "--database", "e2e", "seed-small"],
    {
      cwd: backendDir,
      env: {
        ...process.env,
        ALYA_DATABASE_URL: `sqlite:///${e2eDatabase.split(path.sep).join("/")}`,
      },
      encoding: "utf-8",
      stdio: "pipe",
    }
  );

  if (result.status !== 0) {
    throw new Error(
      `E2E seeding failed (exit ${result.status}).\n${result.stdout ?? ""}\n${result.stderr ?? ""}`
    );
  }
  process.stdout.write("E2E database seeded (seed-small)\n");
}
