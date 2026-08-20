import React, { useEffect, useState, useRef } from 'react';
import {
  Box,
  Typography,
  Alert,
  Stack,
  Accordion,
  AccordionSummary,
  AccordionDetails
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { getRedisCachedMetrics } from '../api/JobApi';
import { METRIC_CATEGORIES } from '../models/Models';

interface JobMetricsProps {
  jobId: string;
  status: string;
}

function formatTimestamp(ts: string) {
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

function formatKey(key: string) {
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function renderValue(key: string, value: any): React.ReactNode {
  if (key.toLowerCase().includes('timestamp') && typeof value === 'string') {
    return formatTimestamp(value);
  }

  if (key.toLowerCase().includes('elapsed_times') && typeof value === 'object') {
    return (
      <Stack spacing={0.25} sx={{ ml: 2 }}>
        {Object.entries(value).map(([subKey, subVal]) => (
          <Box key={subKey} sx={{ display: 'flex', justifyContent: 'space-between' }}>
            <Typography sx={{ fontWeight: 'bold', minWidth: 180 }}>
              {formatKey(subKey)}:
            </Typography>
            <Typography sx={{ whiteSpace: 'pre-wrap', textAlign: 'right', flex: 1 }}>
              {typeof subVal === 'object' ? JSON.stringify(subVal, null, 2) : String(subVal)}
            </Typography>
          </Box>
        ))}
      </Stack>
    );
  }

  if (typeof value === 'object') {
    return <pre>{JSON.stringify(value, null, 2)}</pre>;
  }

  return String(value);
}

function renderKeyValuePairs(obj: Record<string, any>) {
  if (!obj || Object.keys(obj).length === 0) return null;

  return (
    <Stack spacing={0}>
      {Object.entries(obj).map(([key, value], index, arr) => (
        <Box
          key={key}
          sx={{
            display: 'flex',
            justifyContent: 'space-between',
            py: 0.5,
            borderBottom: index !== arr.length - 1 ? '1px solid #e0e0e0' : 'none',
          }}
        >
          <Typography sx={{ minWidth: 180 }}>
            {formatKey(key)}:
          </Typography>
          <Typography sx={{ whiteSpace: 'pre-wrap', textAlign: 'right', flex: 1 }}>
            {renderValue(key, value)}
          </Typography>
        </Box>
      ))}
    </Stack>
  );
}

function groupTopLevelMetrics(metric: Record<string, any>) {
  const initialQuery: Record<string, any> = {};
  const searchResults: Record<string, any> = {};
  const overallRun: Record<string, any> = {};

  for (const key of METRIC_CATEGORIES.initialQueryMetrics) {
    if (metric[key] !== undefined) initialQuery[key] = metric[key];
  }
  for (const key of METRIC_CATEGORIES.searchResultMetrics) {
    if (metric[key] !== undefined) searchResults[key] = metric[key];
  }
  for (const key of METRIC_CATEGORIES.overallRunTimestamps) {
    if (metric[key] !== undefined) overallRun[key] = metric[key];
  }

  return { initialQuery, searchResults, overallRun };
}

function ControlledAccordionSection({
  title,
  data,
  panelKey,
  expanded,
  handleChange
}: {
  title: string;
  data: Record<string, any>;
  panelKey: string;
  expanded: string | false;
  handleChange: (panel: string) => (event: React.SyntheticEvent, isExpanded: boolean) => void;
}) {
  if (!data || Object.keys(data).length === 0) return null;

  return (
    <Accordion
      expanded={expanded === panelKey}
      onChange={handleChange(panelKey)}
      disableGutters
      sx={{ boxShadow: 'none', borderBottom: '1px solid #ddd' }}
    >
      <AccordionSummary
        expandIcon={<ExpandMoreIcon />}
        sx={{ minHeight: 'unset', '& .MuiAccordionSummary-content': { my: 0.5 } }}
      >
        <Typography sx={{ width: '33%', flexShrink: 0, fontWeight: 550 }}>{title}</Typography>
      </AccordionSummary>
      <AccordionDetails sx={{ py: 0.5 }}>
        {renderKeyValuePairs(data)}
      </AccordionDetails>
    </Accordion>
  );
}

function ElapsedTimesAccordion({
  elapsedTimes,
  panelKey,
  expanded,
  handleChange
}: {
  elapsedTimes: Record<string, number>;
  panelKey: string;
  expanded: string | false;
  handleChange: (panel: string) => (event: React.SyntheticEvent, isExpanded: boolean) => void;
}) {
  if (!elapsedTimes || Object.keys(elapsedTimes).length === 0) return null;

  return (
    <Accordion
      expanded={expanded === panelKey}
      onChange={handleChange(panelKey)}
      disableGutters
      sx={{ boxShadow: 'none', borderBottom: '1px solid #ddd' }}
    >
      <AccordionSummary
        expandIcon={<ExpandMoreIcon />}
        sx={{ minHeight: 'unset', '& .MuiAccordionSummary-content': { my: 0.5 } }}
      >
        <Typography sx={{ width: '33%', flexShrink: 0, fontWeight: 550 }}>Elapsed Times</Typography>
      </AccordionSummary>
      <AccordionDetails sx={{ py: 0.5 }}>
        <Stack spacing={0}>
          {Object.entries(elapsedTimes).map(([key, val], index, arr) => (
            <Box
              key={key}
              sx={{
                display: 'flex',
                justifyContent: 'space-between',
                py: 0.5,
                borderBottom: index !== arr.length - 1 ? '1px solid #e0e0e0' : 'none',
              }}
            >
              <Typography sx={{ minWidth: 180 }}>
                {formatKey(key)}:
              </Typography>
              <Typography sx={{ textAlign: 'right' }}>
                {Math.round(val)} s
              </Typography>
            </Box>
          ))}
        </Stack>

      </AccordionDetails>
    </Accordion>
  );
}

export default function JobMetrics({ jobId, status }: JobMetricsProps) {
  const [metrics, setMetrics] = useState<object[]>([]);
  const [metricsError, setMetricsError] = useState('');
  const [expanded, setExpanded] = useState<string | false>(false);
  const wsMetricsRef = useRef<WebSocket | null>(null);

  const handleAccordionChange = (panel: string) => (_: React.SyntheticEvent, isExpanded: boolean) => {
    setExpanded(isExpanded ? panel : false);
  };

  useEffect(() => {
    if (!jobId || !status) return;

    const isDone = ['completed', 'failed', 'interrupted'].includes(status.toLowerCase());
    let ws: WebSocket | null = null;
    let retryTimeout: ReturnType<typeof setTimeout>;

    const fetchCachedMetrics = async () => {
      try {
        const res = await getRedisCachedMetrics(jobId);
        setMetrics(res.metrics || []);
      } catch (err) {
        console.warn('Failed to load cached metrics from Redis.', err);
        setMetricsError('No cached metrics available.');
        setMetrics([]);
      }
    };

    const connectWebSocket = () => {
      if (isDone) return; // Don't open WebSocket if job is done

      const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:8000';
      const wsUrl = apiUrl.replace(/^http/, 'ws');
      ws = new WebSocket(`${wsUrl}/ws/jobs/${jobId}/metrics`);
      wsMetricsRef.current = ws;

      ws.onopen = () => {
        console.log(`Metrics WebSocket connected for job ${jobId}`);
        setMetricsError('');
      };

      ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          setMetrics((prev) => [...prev, parsed]);
        } catch {
          console.warn('Received malformed metric:', event.data);
        }
      };

      ws.onerror = (event) => {
        console.error('Metrics WebSocket error:', event);
        setMetricsError('Metrics WebSocket error occurred. Retrying...');
      };

      ws.onclose = () => {
        console.log(`Metrics WebSocket closed for job ${jobId}.`);
        if (!isDone) {
          retryTimeout = setTimeout(connectWebSocket, 5000);
        }
      };
    };

    fetchCachedMetrics();
    if (!isDone) {
      connectWebSocket();
    }

    return () => {
      if (ws) ws.close();
      clearTimeout(retryTimeout);
      wsMetricsRef.current = null;
    };
  }, [jobId, status]);

  // === Group all incoming metrics into single objects per category ===
  const groupedMetrics = {
    initialQuery: {} as Record<string, any>,
    searchResults: {} as Record<string, any>,
    overallWithoutElapsed: {} as Record<string, any>,
    elapsed_times: {} as Record<string, number>,
  };

  metrics.forEach((metric) => {
    const { initialQuery, searchResults, overallRun } = groupTopLevelMetrics(metric);
    const { elapsed_times, ...overallWithoutElapsed } = overallRun;

    Object.assign(groupedMetrics.initialQuery, initialQuery);
    Object.assign(groupedMetrics.searchResults, searchResults);
    Object.assign(groupedMetrics.overallWithoutElapsed, overallWithoutElapsed);
    Object.assign(groupedMetrics.elapsed_times, elapsed_times);
  });

  return (
    <>
      {metricsError && <Alert severity="warning" sx={{ mb: 1 }}>{metricsError}</Alert>}

      <Box
        sx={{
          backgroundColor: '#f0f0f0',
          color: '#333',
          p: 2,
          borderRadius: 1,
          maxHeight: 300,
          overflowY: 'auto',
          fontSize: 13,
          mb: 2,
        }}
      >
        {metrics.length > 0 ? (
          <>
            <ControlledAccordionSection
              title="Initial Generation Metrics"
              data={groupedMetrics.initialQuery}
              panelKey="initialQuery"
              expanded={expanded}
              handleChange={handleAccordionChange}
            />
            <ControlledAccordionSection
              title="Search Result Metrics"
              data={groupedMetrics.searchResults}
              panelKey="searchResults"
              expanded={expanded}
              handleChange={handleAccordionChange}
            />
            <ControlledAccordionSection
              title="Overall Run Info"
              data={groupedMetrics.overallWithoutElapsed}
              panelKey="overallRun"
              expanded={expanded}
              handleChange={handleAccordionChange}
            />
            <ElapsedTimesAccordion
              elapsedTimes={groupedMetrics.elapsed_times}
              panelKey="elapsedTimes"
              expanded={expanded}
              handleChange={handleAccordionChange}
            />
          </>
        ) : (
          metricsError || <Typography>No metrics available yet.</Typography>
        )}
      </Box>
    </>
  );
}
