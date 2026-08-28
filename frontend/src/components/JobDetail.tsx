import React, { useEffect, useState, useRef } from 'react';
import {
  Box,
  Typography,
  Paper,
  Button,
  Divider,
  Stack,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  IconButton,
} from '@mui/material';

import CloseIcon from '@mui/icons-material/Close';
import {
    getJobProgress,
    getJobDetails,
    interruptJob,
    getStorageLogs,
    getRedisCachedLogs,
    getJobZipDownloadUrl,
    apiErrorMessage
} from '../api/JobApi';
import { JobDetails } from '../models/Models';
import JobMetrics from './JobMetrics';
import FileViewer from './FileViewer';

interface JobDetailProps {
  jobId: string;
  onBack: () => void;
}

export default function JobDetail({ jobId, onBack }: JobDetailProps) {
  const [status, setStatus] = useState('');
  const [progress, setProgress] = useState('');
  const [logs, setLogs] = useState('');
  const [jobInfo, setJobInfo] = useState<JobDetails | null>(null);
  const [interrupting, setInterrupting] = useState(false);
  const [error, setError] = useState('');
  const [wsError, setWsError] = useState('');
  const wsLogRef = useRef<WebSocket | null>(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [fileViewerOpen, setFileViewerOpen] = useState(false);
  const handleOpenFileViewer = () => setFileViewerOpen(true);
  const handleCloseFileViewer = () => setFileViewerOpen(false);


  const handleDownload = async () => {
    try {
        const res = await getJobZipDownloadUrl(jobId);
        if (res.download_url) {
        window.open(res.download_url, '_blank');
        } else {
        setError('No download URL available.');
        }
    } catch (e) {
        console.error('Failed to fetch download URL:', e);
        setError(`Download failed: ${apiErrorMessage(e)}`);
    }
  };


  const getStatusColor = (status: string) => {
    const lower = status.toLowerCase();
    if (lower === 'completed') return 'success.main';
    if (lower === 'running') return 'info.main';
    if (lower === 'failed' || lower === 'interrupted') return 'error.main';
    return 'text.secondary';
  };

  // Poll for job status as before
  useEffect(() => {
    if (!jobId) return;

    const fetchStatus = async () => {
      try {
        const res = await getJobProgress(jobId);
        setStatus(res.status);
        setProgress(res.progress);
      } catch {
        setError('Failed to fetch job status');
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 3000);
    return () => clearInterval(interval);
  }, [jobId]);

  // Poll job metadata until storage_upload_folder is available, then stop polling
  useEffect(() => {
    if (!jobId) return;

    let interval: ReturnType<typeof setInterval>;

    const fetchDetails = async () => {
        try {
            const res = await getJobDetails(jobId);

            setJobInfo((prev) => {
                // Update only if changed
                if (JSON.stringify(prev) !== JSON.stringify(res)) {
                    return res;
                }
                return prev;
            });

            if (res.storage_upload_folder && res.storage_upload_folder.trim() !== '') {
                clearInterval(interval);
            }
        } catch {
            setError('Failed to load job metadata');
        }
    };

    fetchDetails();

    interval = setInterval(fetchDetails, 5000);

    return () => clearInterval(interval);
  }, [jobId]);


  // Setup WebSocket connection for live logs
  useEffect(() => {
    if (!jobId || !status) return;

    const isDone = ['completed', 'failed', 'interrupted'].includes(status.toLowerCase());
    let ws: WebSocket | null = null;
    let retryTimeout: ReturnType<typeof setTimeout>;

    const connectWebSocket = () => {
        const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:8000';
        const wsUrl = apiUrl.replace(/^http/, 'ws');
        ws = new WebSocket(`${wsUrl}/ws/jobs/${jobId}/logs`);
        wsLogRef.current = ws;

        ws.onopen = () => {
            console.log(`WebSocket connected for job ${jobId}`);
            setWsError('');
        };

        ws.onmessage = (event) => {
            console.log('Log message received:', event.data);
            setLogs((prevLogs) => prevLogs + event.data + '\n');
        };

        ws.onerror = (event) => {
            console.error('WebSocket error:', event);
            setWsError('WebSocket error occurred. Retrying...');
        };

        ws.onclose = () => {
            console.log(`WebSocket closed for job ${jobId}. Reconnecting in 5 seconds...`);
            retryTimeout = setTimeout(() => {
                connectWebSocket();
            }, 5000);
        };
    };

    const fetchInitialLogs = async () => {
        try {
            setLogs('Loading logs...');
            const res = await getRedisCachedLogs(jobId);
            const cleanedLogs =
                res.logs.includes('\\n') && !res.logs.includes('\n')
                    ? res.logs.replace(/\\n/g, '\n')
                    : res.logs;

            setLogs(cleanedLogs || '');
        } catch (e) {
            console.warn('Failed to load cached logs from Redis.');
            setLogs('No cached logs available.\n');
        }
    };

    const fetchFinalLogs = async () => {
        try {
            setLogs('Loading final logs...');
            const res = await getStorageLogs(jobId);

            const cleanedLogs =
                res.logs.includes('\\n') && !res.logs.includes('\n')
                ? res.logs.replace(/\\n/g, '\n')
                : res.logs;

            setLogs(cleanedLogs);
        } catch (e) {
            setLogs('Failed to load logs from storage.');
        }
    };

    if (!isDone) {
        fetchInitialLogs(); // Fetch initial cached logs (if any)
        connectWebSocket(); // Start WebSocket for live logs
    } else {
        wsLogRef.current?.close();
        wsLogRef.current = null;
        fetchFinalLogs(); // Job finished – get from storage
    }

    return () => {
        if (ws) ws.close();
        clearTimeout(retryTimeout);
        wsLogRef.current = null;
    };
  }, [jobId, status]);

  const handleInterrupt = async () => {
    if (!jobId) return;
    setInterrupting(true);
    try {
      const res = await interruptJob(jobId);
      setStatus(res.status);
      setProgress(res.message);
    } catch {
      setError('Failed to interrupt job');
    } finally {
      setInterrupting(false);
    }
  };

  if (!jobId) return <Typography>Missing job ID</Typography>;

  return (
    <Paper sx={{ p: 3, mt: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Button onClick={onBack} variant="outlined">
          Back to Dashboard
        </Button>

        <Stack direction="row" spacing={2}>
          {['completed', 'failed', 'interrupted'].includes(status.toLowerCase()) && (
            <Button variant="outlined" onClick={handleOpenFileViewer}>
              View Available Files
            </Button>
          )}

          {['completed', 'failed', 'interrupted'].includes(status.toLowerCase()) ? (
            <Button
              variant="contained"
              color="primary"
              onClick={handleDownload}
            >
              Download ZIP
            </Button>
          ) : (
            <Button
              variant="contained"
              color="error"
              onClick={handleInterrupt}
              disabled={interrupting}
            >
              {interrupting ? 'Interrupting...' : 'Interrupt Job'}
            </Button>
          )}
        </Stack>
      </Stack>
      <Box
        sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            mb: 2,
            p: 2,
            borderRadius: 1,
            backgroundColor: getStatusColor(status),
            color: 'white',
        }}
      >
        <Typography variant="h6" fontWeight="medium">
            Job Details
        </Typography>
        <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
            ID: {jobId}
        </Typography>
      </Box>

      {error && <Alert severity="error">{error}</Alert>}
      {wsError && <Alert severity="warning">{wsError}</Alert>}

      <Divider sx={{ my: 2 }} />

      <Typography variant="h6" gutterBottom>
        Job Parameters
      </Typography>

      {jobInfo ? (
        <>
          <Stack spacing={1} sx={{ mb: 2 }}>
            {[
              ['Mode', jobInfo.mode],
              ['Input', jobInfo.input],
              ['Output Folder', jobInfo.storage_upload_folder || 'N/A'],
              ['Created At', new Date(jobInfo.created_at).toLocaleString()],
            ].map(([label, value]) => (
              <Stack key={label} direction="row" spacing={2}>
                <Typography
                  variant="body2"
                  sx={{ fontWeight: 600, minWidth: 140 }}
                >
                  {label}:
                </Typography>
                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                  {value}
                </Typography>
              </Stack>
            ))}
          </Stack>
        </>
      ) : (
        <Typography>Loading job metadata...</Typography>
      )}

      <Divider sx={{ my: 2 }} />

      <Typography variant="h6" gutterBottom>
        Metrics
      </Typography>

      <JobMetrics jobId={jobId} status={status} />


      <Divider sx={{ my: 2 }} />

      <Typography variant="h6" gutterBottom>
        Logs
      </Typography>

      <Box
        component="pre"
        sx={{
          backgroundColor: '#1e1e1e',
          color: '#00FF00',
          p: 2,
          borderRadius: 1,
          maxHeight: 400,
          overflowY: 'auto',
          fontSize: 12,
          whiteSpace: 'pre-wrap',
        }}
      >
        {logs || 'No logs available yet.'}
      </Box>
      <Dialog
        open={fileViewerOpen}
        onClose={handleCloseFileViewer}
        fullWidth
        maxWidth="lg"
      >
        <DialogTitle sx={{ m: 0, p: 2 }}>
          File Viewer
          <IconButton
            aria-label="close"
            onClick={handleCloseFileViewer}
            sx={{
              position: 'absolute',
              right: 8,
              top: 8,
              color: (theme) => theme.palette.grey[500],
            }}
          >
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent dividers>
          <FileViewer jobId={jobId} />
        </DialogContent>
      </Dialog>
    </Paper>
  );
}
