/*
 * Copyright 2025-2026 IBM Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import FileViewer from "./FileViewer";
import * as api from "../api/JobApi";

// apiErrorMessage stays real: it is used for the error text this component renders.
jest.mock("../api/JobApi", () => ({
  ...jest.requireActual("../api/JobApi"),
  listAvailableFiles: jest.fn(),
  viewFileContent: jest.fn(),
}));

const mockedList = api.listAvailableFiles as jest.MockedFunction<typeof api.listAvailableFiles>;
const mockedView = api.viewFileContent as jest.MockedFunction<typeof api.viewFileContent>;

const TOPICS_ROWS = [{ topic: "sustainable energy", search_queries: ["solar", "wind"], parents: [] }];
const RESULTS_ROWS = [
  { title: "Renewable vs Sustainable", link: "https://example.invalid/a", score: 0.87 },
  { title: "Grid storage", link: "https://example.invalid/b", score: 0.61 },
];

function mockFileList() {
  mockedList.mockResolvedValue({
    job_id: "j",
    available: [
      { file_type: "topics", filename: "topics.jsonl", path: "p", size_bytes: 824, last_modified: null },
      { file_type: "results", filename: "searchresults.jsonl", path: "p", size_bytes: 174951, last_modified: null },
    ],
    missing: [],
  } as any);
}

async function selectResults() {
  await userEvent.click(screen.getByLabelText("Select File"));
  await userEvent.click(await screen.findByText(/searchresults\.jsonl/));
  await waitFor(() => expect(mockedView).toHaveBeenCalledWith("j", "results", 0, 10000));
}

beforeEach(() => {
  jest.clearAllMocks();
  mockFileList();
});

test("renders the selected file's rows and columns", async () => {
  mockedView.mockImplementation(async (_job, fileType) =>
    ({ rows: fileType === "topics" ? TOPICS_ROWS : RESULTS_ROWS } as any)
  );

  render(<FileViewer jobId="j" />);
  await selectResults();

  expect(await screen.findByText("Renewable vs Sustainable")).toBeInTheDocument();
  expect(screen.queryByText("No rows to display.")).not.toBeInTheDocument();
});

test("ignores a response for a file the user has navigated away from", async () => {
  // The topics request is still in flight when the user switches to results, and
  // resolves afterwards. It must not overwrite the results rows.
  mockedView.mockImplementation(async (_job, fileType) => {
    if (fileType === "topics") {
      await new Promise((resolve) => setTimeout(resolve, 200));
      return { rows: TOPICS_ROWS } as any;
    }
    return { rows: RESULTS_ROWS } as any;
  });

  render(<FileViewer jobId="j" />);
  await selectResults();

  await new Promise((resolve) => setTimeout(resolve, 400)); // late topics response lands

  expect(screen.getByText("Renewable vs Sustainable")).toBeInTheDocument();
  expect(screen.queryByText("sustainable energy")).not.toBeInTheDocument();
});
