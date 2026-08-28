import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import JobForm from "./JobForm";
import * as jobApi from "../api/JobApi";

// Only submitJob is stubbed: apiErrorMessage is the code under test for the
// error path, and an auto-mocked version returns undefined, which silently
// swallows the alert this suite asserts on.
jest.mock("../api/JobApi", () => ({
  ...jest.requireActual("../api/JobApi"),
  submitJob: jest.fn(),
}));

const mockedSubmitJob = jobApi.submitJob as jest.MockedFunction<typeof jobApi.submitJob>;

const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

function renderJobForm() {
  return render(
    <MemoryRouter>
      <JobForm />
    </MemoryRouter>
  );
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe("JobForm", () => {
  it("renders the form title and submit button", () => {
    renderJobForm();

    expect(screen.getByText("Submit a Job")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /submit job/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
  });

  it("renders text input fields", () => {
    renderJobForm();

    const textboxes = screen.getAllByRole("textbox");
    expect(textboxes.length).toBeGreaterThanOrEqual(2);
  });

  it("has query mode selected by default", () => {
    renderJobForm();
    expect(screen.getByText("query")).toBeInTheDocument();
  });

  it("renders perform search checkbox unchecked by default", () => {
    renderJobForm();
    const checkbox = screen.getByRole("checkbox");
    expect(checkbox).not.toBeChecked();
  });

  it("submits the form and navigates to job detail page", async () => {
    mockedSubmitJob.mockResolvedValue({ job_id: "new-job-123", status: "queued" });
    renderJobForm();

    const textboxes = screen.getAllByRole("textbox");
    await userEvent.type(textboxes[0], "machine learning");

    fireEvent.click(screen.getByRole("button", { name: /submit job/i }));

    await waitFor(() => {
      expect(mockedSubmitJob).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/job/new-job-123");
    });
  });

  it("shows error alert on submission failure", async () => {
    mockedSubmitJob.mockRejectedValue(new Error("Network error"));
    renderJobForm();

    const textboxes = screen.getAllByRole("textbox");
    await userEvent.type(textboxes[0], "test input");

    fireEvent.click(screen.getByRole("button", { name: /submit job/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });

    expect(screen.getByText(/network error/i)).toBeInTheDocument();
  });

  it("cancel button navigates to dashboard", () => {
    renderJobForm();

    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));

    expect(mockNavigate).toHaveBeenCalledWith("/dashboard");
  });

  it("renders the Mode selector", () => {
    renderJobForm();
    expect(screen.getAllByText("Mode").length).toBeGreaterThan(0);
  });
});
