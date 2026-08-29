/*
 * Copyright 2025-2026 IBM Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

import {
  submitJob,
  getJobProgress,
  getAllJobs,
  getJobDetails,
  getStorageLogs,
  getRedisCachedLogs,
  interruptJob,
  getRedisCachedMetrics,
  getStorageMetrics,
  getJobZipDownloadUrl,
  listAvailableFiles,
  viewFileContent,
} from "./JobApi";
import axios from "axios";

// The mock is defined in src/__mocks__/axios.ts
// axios.create() returns our mockInstance with get/post as jest.fn()
const mockInstance = (axios as any).create();

beforeEach(() => {
  mockInstance.get.mockReset();
  mockInstance.post.mockReset();
});

describe("submitJob", () => {
  it("posts user args to /jobs/ and returns job_id + status", async () => {
    mockInstance.post.mockResolvedValue({ data: { job_id: "abc123", status: "queued" } });

    const args = { mode: "query" as const, input: "test", perform_search: false };
    const result = await submitJob(args);

    expect(mockInstance.post).toHaveBeenCalledWith("/jobs/", args);
    expect(result).toEqual({ job_id: "abc123", status: "queued" });
  });
});

describe("getJobProgress", () => {
  it("gets progress for a job", async () => {
    mockInstance.get.mockResolvedValue({ data: { job_id: "abc", status: "running", progress: "50%" } });

    const result = await getJobProgress("abc");

    expect(mockInstance.get).toHaveBeenCalledWith("/jobs/abc/progress");
    expect(result.progress).toBe("50%");
  });
});

describe("getAllJobs", () => {
  it("returns list of job summaries", async () => {
    const jobs = [
      { job_id: "1", mode: "query", input: "test", status: "completed" },
      { job_id: "2", mode: "topic", input: "math", status: "running" },
    ];
    mockInstance.get.mockResolvedValue({ data: { jobs } });

    const result = await getAllJobs();

    expect(mockInstance.get).toHaveBeenCalledWith("/jobs/");
    expect(result.jobs).toHaveLength(2);
  });
});

describe("getJobDetails", () => {
  it("returns full job details", async () => {
    mockInstance.get.mockResolvedValue({ data: { status: "completed", mode: "query" } });

    const result = await getJobDetails("job-1");

    expect(mockInstance.get).toHaveBeenCalledWith("/jobs/job-1");
    expect(result.status).toBe("completed");
  });
});

describe("getStorageLogs", () => {
  it("fetches storage logs for a job", async () => {
    mockInstance.get.mockResolvedValue({ data: { job_id: "j1", logs: "log line 1\nlog line 2" } });

    const result = await getStorageLogs("j1");

    expect(mockInstance.get).toHaveBeenCalledWith("/jobs/j1/logs/storage");
    expect(result.logs).toContain("log line 1");
  });
});

describe("getRedisCachedLogs", () => {
  it("fetches Redis-cached logs", async () => {
    mockInstance.get.mockResolvedValue({ data: { job_id: "j1", logs: "cached log" } });

    const result = await getRedisCachedLogs("j1");

    expect(mockInstance.get).toHaveBeenCalledWith("/jobs/j1/logs/redis");
    expect(result.logs).toBe("cached log");
  });
});

describe("interruptJob", () => {
  it("posts interrupt and returns status", async () => {
    mockInstance.post.mockResolvedValue({
      data: { job_id: "j1", status: "interrupted", message: "Job interrupted" },
    });

    const result = await interruptJob("j1");

    expect(mockInstance.post).toHaveBeenCalledWith("/jobs/j1/interrupt");
    expect(result.status).toBe("interrupted");
  });
});

describe("getRedisCachedMetrics", () => {
  it("fetches metrics history from Redis", async () => {
    const metrics = [{ generated_queries: 5 }, { generated_queries: 10 }];
    mockInstance.get.mockResolvedValue({ data: { job_id: "j1", metrics } });

    const result = await getRedisCachedMetrics("j1");

    expect(mockInstance.get).toHaveBeenCalledWith("/jobs/j1/metrics/redis");
    expect(result.metrics).toHaveLength(2);
  });
});

describe("getStorageMetrics", () => {
  it("fetches storage metrics", async () => {
    mockInstance.get.mockResolvedValue({ data: { job_id: "j1", metrics: "{}" } });

    const result = await getStorageMetrics("j1");

    expect(mockInstance.get).toHaveBeenCalledWith("/jobs/j1/metrics/storage");
    expect(result.job_id).toBe("j1");
  });
});

describe("getJobZipDownloadUrl", () => {
  it("returns a download URL", async () => {
    mockInstance.get.mockResolvedValue({
      data: { job_id: "j1", download_url: "https://storage.example.com/file.zip" },
    });

    const result = await getJobZipDownloadUrl("j1");

    expect(mockInstance.get).toHaveBeenCalledWith("/jobs/j1/download-zip");
    expect(result.download_url).toContain("file.zip");
  });
});

describe("listAvailableFiles", () => {
  it("returns available and missing files", async () => {
    const data = {
      job_id: "j1",
      available: [{ file_type: "results", filename: "out.jsonl", path: "/path", size_bytes: 1024, last_modified: null }],
      missing: ["topics"],
    };
    mockInstance.get.mockResolvedValue({ data });

    const result = await listAvailableFiles("j1");

    expect(mockInstance.get).toHaveBeenCalledWith("/jobs/j1/files");
    expect(result.available).toHaveLength(1);
    expect(result.missing).toContain("topics");
  });
});

describe("viewFileContent", () => {
  it("fetches paginated file content", async () => {
    const data = {
      job_id: "j1",
      file_type: "results",
      offset: 0,
      limit: 50,
      rows: [{ link: "http://example.com" }],
    };
    mockInstance.get.mockResolvedValue({ data });

    const result = await viewFileContent("j1", "results", 0, 50);

    expect(mockInstance.get).toHaveBeenCalledWith("/jobs/j1/files/view", {
      params: { file_type: "results", offset: 0, limit: 50 },
    });
    expect(result.rows).toHaveLength(1);
  });

  it("uses default offset and limit", async () => {
    mockInstance.get.mockResolvedValue({
      data: { job_id: "j1", file_type: "topics", offset: 0, limit: 50, rows: [] },
    });

    await viewFileContent("j1", "topics");

    expect(mockInstance.get).toHaveBeenCalledWith("/jobs/j1/files/view", {
      params: { file_type: "topics", offset: 0, limit: 50 },
    });
  });
});
