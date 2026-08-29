/*
 * Copyright 2025-2026 IBM Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

import React from "react";
import {
  Stack,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Checkbox,
  FormControlLabel,
  Typography,
  Paper,
} from "@mui/material";
import { Annotation, OutputFormat } from "../models/Models";
import AnnotationsSelector from "./AnnotationsSelector";

interface Props {
  maxResultsPerQuery: number | undefined;
  outputFormat: OutputFormat | undefined;
  filterResults: boolean | undefined;
  annotations: Annotation[] | undefined;
  disabled?: boolean;

  onChange: (field: string, value: any) => void;
  onAnnotationChange: (annotation: Annotation, checked: boolean) => void;
}

const SearchOptions: React.FC<Props> = ({
  maxResultsPerQuery,
  outputFormat,
  filterResults,
  annotations,
  disabled,
  onChange,
  onAnnotationChange,
}) => {
  return (
    <Paper
      elevation={1}
      sx={{ p: 3, mt: 3, borderRadius: 2, border: "1px solid #ddd" }}
      component="section"
      aria-labelledby="search-options-heading"
    >
      <Typography id="search-options-heading" variant="h6" gutterBottom>
        Search Options
      </Typography>

      <Stack spacing={3}>
        <TextField
            label="Max Results per Query"
            type="number"
            value={maxResultsPerQuery ?? ""}
            onChange={(e) => {
                let value = Number(e.target.value);
                if (value > 1000) value = 1000;
                if (value < 1) value = 1;
                onChange("max_results_per_query", value);
            }}
            disabled={disabled}
            inputProps={{ min: 1, max: 1000 }}
            fullWidth
            helperText="Maximum number of results to fetch per query (max 1000)."
        />

        <FormControl fullWidth disabled={disabled}>
          <InputLabel id="output-format-label">Output Format</InputLabel>
          <Select
            labelId="output-format-label"
            value={outputFormat ?? ""}
            label="Output Format"
            onChange={(e) => onChange("output_format", e.target.value)}
          >
            <MenuItem value="jsonl">JSONL</MenuItem>
            <MenuItem value="parquet">Parquet</MenuItem>
          </Select>
        </FormControl>

        {/* Box around AnnotationsSelector */}
        <Paper
          elevation={0}
          variant="outlined"
          sx={{
            p: 2,
            border: "1px solid #ccc",
            borderRadius: 1,
          }}
        >
          <AnnotationsSelector
            selected={annotations}
            onChange={onAnnotationChange}
            disabled={disabled}
          />
        </Paper>

        <FormControlLabel
          control={
            <Checkbox
              checked={filterResults ?? false}
              onChange={(e) => onChange("filter_results", e.target.checked)}
              disabled={disabled}
            />
          }
          label={<Typography sx={{ fontWeight: "bold" }}>Filter Results</Typography>}
        />
      </Stack>
    </Paper>
  );
};

export default SearchOptions;
