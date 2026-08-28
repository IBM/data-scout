import axios from "axios";
import { UserArgs, JobSummary, JobDetails } from "../models/Models";

const headers: Record<string, string> = {};
if (process.env.REACT_APP_API_KEY) {
  headers["X-API-Key"] = process.env.REACT_APP_API_KEY;
}

const api = axios.create({
  baseURL: process.env.REACT_APP_API_URL || 'http://localhost:8000',
  headers,
});

/**
 * Turn an axios failure into something an operator can act on. The API reports
 * real causes in `detail`; axios only ever exposes "Request failed with status
 * code N" via `message`, and reduces a request that got no response at all to a
 * bare "Network Error" with no mention of which host was unreachable.
 */
export function apiErrorMessage(err: any): string {
  const detail = err?.response?.data?.detail;
  if (detail) {
    return typeof detail === "string" ? detail : JSON.stringify(detail);
  }
  if (err?.response) {
    return `${err.response.status} ${err.response.statusText || ""}`.trim();
  }
  if (err?.request) {
    return `No response from API at ${api.defaults.baseURL} — check that it is running and reachable.`;
  }
  return err?.message || "Request failed";
}

export async function submitJob(args: UserArgs): Promise<{ job_id: string; status: string }> {
  const response = await api.post("/jobs/", args);
  return response.data;
}

export async function getJobProgress(jobId: string): Promise<{
  job_id: string;
  status: string;
  progress: string;
}> {
  const response = await api.get(`/jobs/${jobId}/progress`);
  return response.data;
}

export async function getAllJobs(): Promise<{ jobs: JobSummary[] }> {
  const response = await api.get("/jobs/");
  return response.data;
}

export async function getJobDetails(jobId: string): Promise<JobDetails> {
  const response = await api.get(`/jobs/${jobId}`);
  return response.data;
}

export async function getStorageLogs(jobId: string): Promise<{ job_id: string; logs: string }> {
  const response = await api.get(`/jobs/${jobId}/logs/storage`);
  return response.data;
}

export async function getRedisCachedLogs(jobId: string): Promise<{ job_id: string; logs: string }> {
  const response = await api.get(`/jobs/${jobId}/logs/redis`);
  return response.data;
}

export async function interruptJob(jobId: string): Promise<{ job_id: string; status: string; message: string }> {
  const response = await api.post(`/jobs/${jobId}/interrupt`);
  return response.data;
}

export async function getRedisCachedMetrics(jobId: string): Promise<{ job_id: string; metrics: any[] }> {
  const response = await api.get(`/jobs/${jobId}/metrics/redis`);
  return response.data;
}

export async function getStorageMetrics(jobId: string): Promise<{ job_id: string; metrics: string }> {
  const response = await api.get(`/jobs/${jobId}/metrics/storage`);
  return response.data;
}

export async function getJobZipDownloadUrl(jobId: string): Promise<{ job_id: string; download_url: string }> {
  const response = await api.get(`/jobs/${jobId}/download-zip`);
  return response.data;
}

export async function listAvailableFiles(jobId: string): Promise<{
  job_id: string;
  available: Array<{
    file_type: string;
    filename: string;
    path: string;
    size_bytes: number;
    last_modified: string | null;
  }>;
  missing: string[];
}> {
  const response = await api.get(`/jobs/${jobId}/files`);
  return response.data;
}

export async function viewFileContent(
  jobId: string,
  fileType: "topics" | "results",
  offset = 0,
  limit = 50
): Promise<{
  job_id: string;
  file_type: string;
  offset: number;
  limit: number;
  rows: any[];
  schema?: string[];
}> {
  const response = await api.get(`/jobs/${jobId}/files/view`, {
    params: { file_type: fileType, offset, limit },
  });
  return response.data;
}
