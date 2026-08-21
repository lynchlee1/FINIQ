import { lstat, readFile, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptsDirectory = path.dirname(fileURLToPath(import.meta.url));
const appDirectory = path.resolve(
  scriptsDirectory,
  "../finiq_GUI/apps/market-desk",
);
const packagePath = path.join(appDirectory, "package.json");
const nextDirectory = path.join(appDirectory, ".next");
const devDirectory = path.join(nextDirectory, "dev");
const lockPath = path.join(devDirectory, "lock");

const appPackage = JSON.parse(await readFile(packagePath, "utf8"));
if (appPackage.name !== "@finiq/app-market-desk") {
  throw new Error(`Unexpected Market Desk package: ${packagePath}`);
}
if (path.basename(devDirectory) !== "dev" || path.basename(nextDirectory) !== ".next") {
  throw new Error(`Refusing to clean unexpected Next.js path: ${devDirectory}`);
}

const pathInfo = async (target) => {
  try {
    return await lstat(target);
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
};

const lockInfo = await pathInfo(lockPath);
if (lockInfo) {
  const lock = JSON.parse(await readFile(lockPath, "utf8"));
  const pid = Number(lock.pid);
  if (Number.isInteger(pid) && pid > 0) {
    try {
      process.kill(pid, 0);
      throw new Error(
        `Market Desk dev server is still running (PID ${pid}). Stop it before restarting.`,
      );
    } catch (error) {
      if (error?.code !== "ESRCH") throw error;
    }
  }
}

const nextInfo = await pathInfo(nextDirectory);
if (nextInfo?.isSymbolicLink()) {
  throw new Error(`Refusing to clean symlinked Next.js cache: ${nextDirectory}`);
}
const devInfo = await pathInfo(devDirectory);
if (devInfo?.isSymbolicLink()) {
  throw new Error(`Refusing to clean symlinked Next.js dev cache: ${devDirectory}`);
}
if (devInfo && !devInfo.isDirectory()) {
  throw new Error(`Next.js dev cache is not a directory: ${devDirectory}`);
}

if (devInfo) {
  await rm(devDirectory, { recursive: true });
  console.log(`Removed stale Market Desk Turbopack cache: ${devDirectory}`);
}
