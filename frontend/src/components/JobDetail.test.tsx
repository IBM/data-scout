import React from "react";
import { render, screen, waitFor, act } from "@testing-library/react";
import JobDetail from "./JobDetail";
import * as api from "../api/JobApi";

jest.mock("../api/JobApi", () => ({
  ...jest.requireActual("../api/JobApi"),
  getJobProgress: jest.fn(),
  getJobDetails: jest.fn(),
  getRedisCachedLogs: jest.fn(),
  getStorageLogs: jest.fn(),
  getRedisCachedMetrics: jest.fn(),
  interruptJob: jest.fn(),
  getJobZipDownloadUrl: jest.fn(),
}));

const mockedProgress = api.getJobProgress as jest.MockedFunction<typeof api.getJobProgress>;
const mockedDetails = api.getJobDetails as jest.MockedFunction<typeof api.getJobDetails>;
const mockedRedisLogs = api.getRedisCachedLogs as jest.MockedFunction<typeof api.getRedisCachedLogs>;
const mockedStorageLogs = api.getStorageLogs as jest.MockedFunction<typeof api.getStorageLogs>;
const mockedMetrics = api.getRedisCachedMetrics as jest.MockedFunction<typeof api.getRedisCachedMetrics>;

/** Records every socket opened, and models a browser's asynchronous onclose. */
class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: any) => void) | null = null;
  onerror: ((e: any) => void) | null = null;
  onclose: ((e: any) => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }
  // The browser dispatches close asynchronously -- *after* React's effect
  // cleanup has already returned. That ordering is the whole bug in audit #6.
  close() {
    this.closed = true;
    Promise.resolve().then(() => this.onclose?.({ code: 1006 }));
  }
  /** Server-initiated close, e.g. 1008 policy violation when API_KEY is set. */
  serverClose(code: number) {
    this.onclose?.({ code });
  }
}

const realWebSocket = global.WebSocket;

beforeEach(() => {
  jest.clearAllMocks();
  FakeWebSocket.instances = [];
  (global as any).WebSocket = FakeWebSocket;
  jest.useFakeTimers();

  mockedProgress.mockResolvedValue({ job_id: "j1", status: "running", progress: "working" } as any);
  mockedDetails.mockResolvedValue({
    mode: "query", input: "topic", storage_upload_folder: "results/x/j1",
    created_at: new Date(0).toISOString(),
  } as any);
  mockedRedisLogs.mockResolvedValue({ job_id: "j1", logs: "line one" } as any);
  mockedStorageLogs.mockResolvedValue({ job_id: "j1", logs: "final" } as any);
  mockedMetrics.mockResolvedValue({ job_id: "j1", metrics: [] } as any);
});

afterEach(() => {
  jest.runOnlyPendingTimers();
  jest.useRealTimers();
  (global as any).WebSocket = realWebSocket;
});

/** Flush the promise queue while fake timers are installed. */
async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

async function renderRunning() {
  const view = render(<JobDetail jobId="j1" onBack={() => {}} />);
  await flush();
  await waitFor(() => expect(FakeWebSocket.instances.length).toBeGreaterThanOrEqual(1));
  return view;
}

describe("JobDetail live-log WebSocket lifecycle (audit #6)", () => {
  it("opens a log socket for a running job", async () => {
    await renderRunning();
    expect(FakeWebSocket.instances.some((w) => w.url.includes("/ws/jobs/j1/logs"))).toBe(true);
  });

  it("does not reconnect after unmount", async () => {
    const { unmount } = await renderRunning();
    const logSockets = () =>
      FakeWebSocket.instances.filter((w) => w.url.includes("/ws/jobs/j1/logs")).length;
    const before = logSockets();

    unmount();
    // Let the asynchronous onclose land, then run out the 5s retry window.
    await flush();
    await act(async () => {
      jest.advanceTimersByTime(30000);
      await Promise.resolve();
    });

    expect(logSockets()).toBe(before);
  });

  it("closes the socket on unmount", async () => {
    const { unmount } = await renderRunning();
    const ws = FakeWebSocket.instances.find((w) => w.url.includes("/logs"))!;
    unmount();
    expect(ws.closed).toBe(true);
  });

  it("stops retrying when the API rejects the handshake with 1008", async () => {
    await renderRunning();
    const ws = FakeWebSocket.instances.find((w) => w.url.includes("/logs"))!;
    const before = FakeWebSocket.instances.length;

    await act(async () => {
      ws.serverClose(1008);
      await Promise.resolve();
    });
    await act(async () => {
      jest.advanceTimersByTime(30000);
      await Promise.resolve();
    });

    expect(FakeWebSocket.instances.length).toBe(before);
    expect(await screen.findByText(/API_KEY is set/i)).toBeInTheDocument();
  });

  it("still reconnects on a transient drop while mounted", async () => {
    await renderRunning();
    const ws = FakeWebSocket.instances.find((w) => w.url.includes("/logs"))!;
    const before = FakeWebSocket.instances.length;

    await act(async () => {
      ws.serverClose(1006); // abnormal closure, not a policy rejection
      await Promise.resolve();
    });
    await act(async () => {
      jest.advanceTimersByTime(5000);
      await Promise.resolve();
    });

    expect(FakeWebSocket.instances.length).toBeGreaterThan(before);
  });

  it("does not open a socket for a finished job, and loads logs from storage", async () => {
    mockedProgress.mockResolvedValue({ job_id: "j1", status: "completed", progress: "done" } as any);
    render(<JobDetail jobId="j1" onBack={() => {}} />);
    await flush();
    await waitFor(() => expect(mockedStorageLogs).toHaveBeenCalled());
    expect(FakeWebSocket.instances.filter((w) => w.url.includes("/logs"))).toHaveLength(0);
  });
});
