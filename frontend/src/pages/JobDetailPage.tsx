/*
 * Copyright 2025-2026 IBM Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import JobDetail from '../components/JobDetail';

export default function JobDetailPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();

  if (!jobId) {
    return <div>No Job ID provided</div>;
  }

  return <JobDetail jobId={jobId} onBack={() => navigate('/dashboard')} />;
}
