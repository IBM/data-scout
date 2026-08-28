import React, { useState, ChangeEvent } from "react";
import {
  Paper,
  TextField,
  Button,
  Stack,
  Typography,
  Checkbox,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  FormControlLabel,
  Alert,
  Divider,
  Box,
} from "@mui/material";
import { useNavigate } from "react-router-dom";
import ModeSelector from "./ModeSelector";
import { UserArgs, defaultUserArgs, Annotation } from "../models/Models";
import { submitJob, apiErrorMessage } from "../api/JobApi";
import AnnotationsSelector from "./AnnotationsSelector";
import SearchOptions from "./SearchOptions";
// import ModeSelector from "./ModeSelector";  // no longer needed
import RecursionDepthInput from "./RecursionDepthInput";

export default function JobForm() {
  const [args, setArgs] = useState<UserArgs>(defaultUserArgs);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ job_id?: string; status?: string; error?: string } | null>(null);
  const navigate = useNavigate();

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const { name, value, type, checked } = e.target;

    const newValue =
      type === "checkbox"
        ? checked
        : ["recursion_depth", "max_results_per_query"].includes(name)
        ? Number(value)
        : value;

    setArgs((prev) => ({
      ...prev,
      [name]: newValue,
    }));
  }

  function handleAnnotationChange(annotation: Annotation, checked: boolean) {
    setArgs((prev) => {
      const annotations = prev.annotations || [];
      const updated = checked
        ? [...annotations, annotation]
        : annotations.filter((a) => a !== annotation);
      return { ...prev, annotations: updated };
    });
  }

  const showRecursion = args.mode === "topic";
  const showSearchOptions = args.perform_search;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setResult(null);

    try {
        const data = await submitJob(args);
        // Navigate to job detail page after submission
        navigate(`/job/${data.job_id}`);
    } catch (err: any) {
        setResult({ error: apiErrorMessage(err) });
    } finally {
        setSubmitting(false);
    }
  }

  return (
    <Paper sx={{ maxWidth: 700, mx: "auto", mt: 4, p: 4 }}>
      <Typography variant="h5" gutterBottom>
        Submit a Job
      </Typography>

      <form onSubmit={handleSubmit}>
        <Stack spacing={3}>
          {/* Updated Mode Selector */}
          <Box>
            <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: "bold" }}>
              Mode
            </Typography>
            <ModeSelector
                value={args.mode}
                disabled={submitting}
                onChange={(newMode) =>
                    setArgs((prev) => ({
                        ...prev,
                        mode: newMode,
                        perform_search: newMode === "search",
                    }))
                }
            />

          </Box>

          {/* Input Field */}
          <TextField
            label="Input"
            name="input"
            value={args.input}
            onChange={handleChange}
            required
            disabled={submitting}
            fullWidth
          />

          {/* Output Folder */}
          <TextField
            label="Output Folder Name"
            name="output_folder_name"
            value={args.output_folder_name}
            onChange={handleChange}
            disabled={submitting}
            fullWidth
          />

          {/* Recursion Depth */}
          {showRecursion && (
            <RecursionDepthInput
              value={args.recursion_depth}
              disabled={submitting}
              onChange={(newVal) => setArgs((prev) => ({ ...prev, recursion_depth: newVal }))}
            />
          )}

          {/* Perform Search with styled label */}
          <FormControlLabel
            control={
              <Checkbox
                name="perform_search"
                checked={args.perform_search}
                onChange={handleChange}
                disabled={args.mode === "search" || submitting}
              />
            }
            label={
              <Typography variant="subtitle1" sx={{ fontWeight: "bold" }}>
                Perform Search
              </Typography>
            }
          />

          {/* Search Options */}
          {showSearchOptions && (
            <SearchOptions
              maxResultsPerQuery={args.max_results_per_query}
              outputFormat={args.output_format}
              filterResults={args.filter_results}
              annotations={args.annotations}
              disabled={submitting}
              onChange={(field, value) => setArgs((prev) => ({ ...prev, [field]: value }))}
              onAnnotationChange={handleAnnotationChange}
            />
          )}

          <Divider />

          {/* Buttons */}
          <Box display="flex" justifyContent="flex-end" gap={2}>
            <Button variant="outlined" onClick={() => navigate("/dashboard")} disabled={submitting}>
              Cancel
            </Button>
            <Button type="submit" variant="contained" disabled={submitting}>
              {submitting ? "Submitting..." : "Submit Job"}
            </Button>
          </Box>

          {/* Submission Result */}
          {result && (
            <Box mt={2}>
              {result.error && <Alert severity="error">Error: {result.error}</Alert>}
              {result.job_id && (
                <Alert severity="success" sx={{ whiteSpace: "pre-line" }}>
                  Job Submitted!{"\n"}
                  <strong>Job ID:</strong> {result.job_id}{"\n"}
                  <strong>Status:</strong> {result.status}
                </Alert>
              )}
            </Box>
          )}
        </Stack>
      </form>
    </Paper>
  );
}
