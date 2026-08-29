/*
 * Copyright 2025-2026 IBM Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useState } from 'react';
import {
  Container,
  Paper,
  Typography,
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
  CircularProgress,
  Chip,
  Box,
  Stack
} from '@mui/material';
import DashboardIcon from '@mui/icons-material/Dashboard'
import { useNavigate } from 'react-router-dom';
import { getAllJobs } from '../api/JobApi';
import { JobSummary } from '../models/Models';
import WorkOutlineIcon from '@mui/icons-material/WorkOutline';
import TuneIcon from '@mui/icons-material/Tune';
import InputIcon from '@mui/icons-material/Input';
import HourglassBottomIcon from '@mui/icons-material/HourglassBottom';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';

export default function JobDashboard({ onSelectJob }: { onSelectJob: (jobId: string) => void }) {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    getAllJobs()
      .then((res) => setJobs(res.jobs))
      .finally(() => setLoading(false));
  }, []);

  const getStatusChip = (status?: string | null) => {
    const colorMap: Record<string, "default" | "success" | "warning" | "error" | "info"> = {
      completed: "success",
      running: "info",
      queued: "warning",
      failed: "error",
      interrupted: "default",
    };

    // A job whose args were recorded but whose status never was (e.g. the task
    // failed to enqueue) leaves status null. Reading .charAt on that threw and
    // took the whole dashboard down with a blank page, so render it as unknown.
    const label = status
      ? status.charAt(0).toUpperCase() + status.slice(1)
      : "Unknown";

    return (
      <Chip
        label={label}
        color={(status && colorMap[status]) || "default"}
        size="small"
        variant="outlined"
      />
    );
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="40vh">
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Container maxWidth={false} disableGutters>
      <Paper elevation={3} sx={{ p: 3, mt: 4 }}>
        <Stack direction="row" spacing={1} justifyContent="center" alignItems="center" sx={{ mb: 4 }}>
          <DashboardIcon color="primary" fontSize="large" />
          <Typography
            variant="h4"
            sx={{
              fontWeight: 400,
              letterSpacing: 1,
              color: 'primary.main',
            }}
          >
            Job Dashboard
          </Typography>
        </Stack>

        <Table size="small" aria-label="Job dashboard table" sx={{ tableLayout: 'auto' }}>
          <TableHead>
            <TableRow
              sx={{
                backgroundColor: 'grey.100',
                '& th': {
                    fontWeight: 'bold',
                    fontSize: '0.875rem',
                    textTransform: 'uppercase',
                    letterSpacing: 0.5,
                },
              }}
            >
              <TableCell sx={{ width: '15%', textAlign: 'left' }}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <WorkOutlineIcon fontSize="small" />
                  <Box component="span" sx={{ whiteSpace: 'nowrap' }}>
                    Job ID
                  </Box>
                </Stack>
              </TableCell>

              <TableCell sx={{ width: '15%', textAlign: 'left' }}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <TuneIcon fontSize="small" />
                  <Box component="span">Mode</Box>
                </Stack>
              </TableCell>

              <TableCell sx={{ width: '40%', textAlign: 'left' }}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <InputIcon fontSize="small" />
                  <Box component="span">Input</Box>
                </Stack>
              </TableCell>

              <TableCell sx={{ width: '15%', textAlign: 'center' }}>
                <Stack direction="row" spacing={1} justifyContent="center" alignItems="center">
                  <HourglassBottomIcon fontSize="small" />
                  <Box component="span">Status</Box>
                </Stack>
              </TableCell>

              <TableCell sx={{ width: '15%', textAlign: 'center' }}>
                <Stack direction="row" spacing={1} justifyContent="center" alignItems="center">
                  <CheckCircleOutlineIcon fontSize="small" />
                  <Box component="span">Progress</Box>
                </Stack>
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {jobs.map((job) => (
              <TableRow
                key={job.job_id}
                hover
                sx={{ cursor: 'pointer' }}
                onClick={() => onSelectJob(job.job_id)}
              >
                <TableCell>{job.job_id.slice(0, 8)}</TableCell>
                <TableCell>{job.mode}</TableCell>
                <TableCell>{job.input}</TableCell>
                <TableCell align="center">{getStatusChip(job.status)}</TableCell>
                <TableCell align="center" sx={{ whiteSpace: 'normal', maxHeight: 100, overflowY: 'auto', wordBreak: 'break-word' }}>
                  {job.progress || '-'}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
    </Container>
  );
}
