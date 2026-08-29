/*
 * Copyright 2025-2026 IBM Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

const mockGet = jest.fn();
const mockPost = jest.fn();

const mockInstance = {
  get: mockGet,
  post: mockPost,
  put: jest.fn(),
  delete: jest.fn(),
  patch: jest.fn(),
  interceptors: {
    request: { use: jest.fn() },
    response: { use: jest.fn() },
  },
};

const axios: any = {
  create: jest.fn(() => mockInstance),
  get: mockGet,
  post: mockPost,
  defaults: { headers: { common: {} } },
};

export default axios;
