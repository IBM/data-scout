/*
 * Copyright 2025-2026 IBM Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import App from './App';
import * as JobApi from './api/JobApi';

jest.mock("./api/JobApi");

const mockedGetAllJobs = JobApi.getAllJobs as jest.MockedFunction<typeof JobApi.getAllJobs>;

beforeEach(() => {
  mockedGetAllJobs.mockResolvedValue({ jobs: [] });
});

test('renders app with Data Scout title', async () => {
  render(<App />);
  await waitFor(() => {
    expect(screen.getByText(/Data Scout/i)).toBeInTheDocument();
  });
});

test('renders Create New Job button', async () => {
  render(<App />);
  await waitFor(() => {
    expect(screen.getByText(/Create New Job/i)).toBeInTheDocument();
  });
});
