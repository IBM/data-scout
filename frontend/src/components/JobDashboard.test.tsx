import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import JobDashboard from "./JobDashboard";
import * as jobApi from "../api/JobApi";

jest.mock("../api/JobApi");

const mockedGetAllJobs = jobApi.getAllJobs as jest.MockedFunction<typeof jobApi.getAllJobs>;

beforeEach(() => {
  jest.clearAllMocks();
});

function renderDashboard(onSelectJob = jest.fn()) {
  return render(
    <MemoryRouter>
      <JobDashboard onSelectJob={onSelectJob} />
    </MemoryRouter>
  );
}

describe("JobDashboard", () => {
  it("shows loading spinner initially", () => {
    mockedGetAllJobs.mockReturnValue(new Promise(() => {}));
    renderDashboard();

    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("renders job list after loading", async () => {
    mockedGetAllJobs.mockResolvedValue({
      jobs: [
        { job_id: "abc12345-long-id", mode: "query", input: "machine learning", status: "completed" },
        { job_id: "def67890-another", mode: "topic", input: "physics", status: "running" },
      ],
    });

    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText("machine learning")).toBeInTheDocument();
    });

    expect(screen.getByText("physics")).toBeInTheDocument();
    expect(screen.getByText("query")).toBeInTheDocument();
    expect(screen.getByText("topic")).toBeInTheDocument();
  });

  it("displays status chips with correct text", async () => {
    mockedGetAllJobs.mockResolvedValue({
      jobs: [
        { job_id: "id-1", mode: "query", input: "test", status: "completed" },
        { job_id: "id-2", mode: "query", input: "test2", status: "failed" },
      ],
    });

    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText("Completed")).toBeInTheDocument();
    });
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("calls onSelectJob when a row is clicked", async () => {
    const onSelectJob = jest.fn();
    mockedGetAllJobs.mockResolvedValue({
      jobs: [
        { job_id: "click-me-id-full", mode: "query", input: "clickable", status: "completed" },
      ],
    });

    renderDashboard(onSelectJob);

    await waitFor(() => {
      expect(screen.getByText("clickable")).toBeInTheDocument();
    });

    screen.getByText("clickable").closest("tr")!.click();

    expect(onSelectJob).toHaveBeenCalledWith("click-me-id-full");
  });

  it("shows truncated job IDs", async () => {
    mockedGetAllJobs.mockResolvedValue({
      jobs: [
        { job_id: "abcdefgh12345678", mode: "query", input: "test", status: "queued" },
      ],
    });

    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText("abcdefgh")).toBeInTheDocument();
    });
    expect(screen.queryByText("abcdefgh12345678")).not.toBeInTheDocument();
  });

  it("shows dash for missing progress", async () => {
    mockedGetAllJobs.mockResolvedValue({
      jobs: [
        { job_id: "id-no-progress", mode: "query", input: "no progress", status: "queued" },
      ],
    });

    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText("-")).toBeInTheDocument();
    });
  });
});
