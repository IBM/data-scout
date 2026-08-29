/*
 * Copyright 2025-2026 IBM Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

// src/components/FileViewer.tsx
import React, { useEffect, useState } from "react";
import {
  Box,
  Typography,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Button,
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
  TableFooter,
  TablePagination,
  CircularProgress,
  Alert,
  SelectChangeEvent,
  Checkbox,
  ListItemText,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Chip,
  Stack,
} from "@mui/material";
import { listAvailableFiles, viewFileContent, apiErrorMessage } from "../api/JobApi";

interface FileViewerProps {
  jobId: string;
}

interface ExpandableListProps {
  items: any[];
  maxVisible?: number;
}

function ExpandableList({ items, maxVisible = 3 }: ExpandableListProps) {
  const [expanded, setExpanded] = useState(false);
  const toggleExpanded = () => setExpanded(!expanded);

  const visibleItems = expanded ? items : items.slice(0, maxVisible);
  const hiddenCount = items.length - maxVisible;

  return (
    <Box>
      <ul style={{ paddingLeft: "1.2em", margin: 0 }}>
        {visibleItems.map((item, idx) => (
          <li key={idx}>
            {typeof item === "object" ? JSON.stringify(item) : item}
          </li>
        ))}
      </ul>
      {items.length > maxVisible && (
        <Button
          size="small"
          onClick={toggleExpanded}
          sx={{ mt: 0.5, textTransform: "none", paddingLeft: 0 }}
        >
          {expanded ? "Show Less" : `Show ${hiddenCount} More`}
        </Button>
      )}
    </Box>
  );
}

export default function FileViewer({ jobId }: FileViewerProps) {
  const [availableFiles, setAvailableFiles] = useState<
    {
      file_type: string;
      filename: string;
      path: string;
      size_bytes: number;
      last_modified: string | null;
    }[]
  >([]);
  const [selectedFile, setSelectedFile] = useState<string>("");
  const [allRows, setAllRows] = useState<any[]>([]); // All fetched data, unfiltered
  const [filteredRows, setFilteredRows] = useState<any[]>([]); // Rows after filtering
  const [offset, setOffset] = useState(0);
  const [limit] = useState(50);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [schema, setSchema] = useState<string[] | null>(null);
  const [selectedColumns, setSelectedColumns] = useState<string[]>([]);
  const [filterDialogOpen, setFilterDialogOpen] = useState(false);
  const [filters, setFilters] = useState<{ column: string; value: string }[]>([]);

  // Fetch files list
  useEffect(() => {
    async function fetchFiles() {
      setError(null);
      try {
        const data = await listAvailableFiles(jobId);
        setAvailableFiles(data.available);
        if (data.available.length > 0) {
          setSelectedFile(data.available[0].file_type);
          setOffset(0);
          setAllRows([]);
          setFilteredRows([]);
          setSchema(null);
          setSelectedColumns([]);
          setFilters([]);
        }
      } catch {
        setError("Failed to list files.");
      }
    }
    fetchFiles();
  }, [jobId]);

  // Fetch file content (unfiltered)
  useEffect(() => {
    if (!selectedFile) return;

    // Selecting another file supersedes this request. Without this guard a slow
    // response for the file you just navigated away from lands last and wins,
    // leaving the table showing one file's rows under the other file's name.
    let superseded = false;

    async function fetchFileContent() {
      setLoading(true);
      setError(null);
      try {
        const data = await viewFileContent(
          jobId,
          selectedFile as "topics" | "results",
          0, // always fetch first page from API, we'll paginate locally filtered data
          10000 // fetch a large chunk for local filtering & pagination; adjust as needed or implement backend paging
        );
        if (superseded) return;

        setAllRows(data.rows);
        setFilteredRows(data.rows);
        const newSchema = data.schema || (data.rows.length > 0 ? Object.keys(data.rows[0]) : []);
        setSchema(newSchema);
        setSelectedColumns(newSchema);
        setOffset(0);
      } catch (e) {
        if (superseded) return;
        setError(`Failed to load file content: ${apiErrorMessage(e)}`);
      } finally {
        if (!superseded) setLoading(false);
      }
    }
    fetchFileContent();

    return () => {
      superseded = true;
    };
  }, [jobId, selectedFile]);

  // Pagination - this is local pagination of filteredRows
  const currentPageRows = filteredRows.slice(offset, offset + limit);

  // Handle file change
  const handleChangeFile = (event: SelectChangeEvent<string>) => {
    setSelectedFile(event.target.value);
    setOffset(0);
    setAllRows([]);
    setFilteredRows([]);
    setSchema(null);
    setSelectedColumns([]);
    setFilters([]);
  };

  const handleChangePage = (
    event: React.MouseEvent<HTMLButtonElement> | null,
    newPage: number
  ) => {
    setOffset(newPage * limit);
  };

  const toggleSelectAllColumns = () => {
    if (!schema) return;
    setSelectedColumns((prev) => (prev.length === schema.length ? [] : schema));
  };

  const isAllSelected = schema && selectedColumns.length === schema.length;

  const handleColumnSelectionChange = (event: SelectChangeEvent<string[]>) => {
    const value = event.target.value;
    setSelectedColumns(typeof value === "string" ? value.split(",") : value);
  };

  const columns = schema || [];

  // Apply all filters on allRows locally
  const applyFilters = () => {
    if (filters.length === 0) {
      setFilteredRows(allRows);
      setOffset(0);
      return;
    }

    const filtered = allRows.filter((row) => {
      return filters.every(({ column, value }) => {
        if (value === "") return true; // ignore empty filter values
        return String(row[column] ?? "").toLowerCase().includes(value.toLowerCase());
      });
    });

    setFilteredRows(filtered);
    setOffset(0);
  };

  // When filters change, re-apply filters
  useEffect(() => {
    applyFilters();
  }, [filters, allRows]);

  // Add new filter from dialog
  const [tempFilter, setTempFilter] = useState<{ column: string; value: string }>({
    column: "",
    value: "",
  });

  const handleAddFilter = () => {
    if (tempFilter.column && tempFilter.value) {
      setFilters((prev) => [...prev, tempFilter]);
      setTempFilter({ column: "", value: "" });
      setFilterDialogOpen(false);
    }
  };

  // Remove one filter by index
  const handleRemoveFilter = (index: number) => {
    setFilters((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <Box sx={{ mt: 3, width: "100%" }}>
      {error && <Alert severity="error">{error}</Alert>}

      <FormControl sx={{ minWidth: 200, mb: 2, width: "100%" }}>
        <InputLabel id="file-select-label">Select File</InputLabel>
        <Select
          labelId="file-select-label"
          value={selectedFile}
          label="Select File"
          onChange={handleChangeFile}
          disabled={availableFiles.length === 0}
        >
          {availableFiles.map((file) => (
            <MenuItem key={file.file_type} value={file.file_type}>
              {file.filename} ({file.file_type})
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      {schema && (
        <Box sx={{ mb: 2, display: "flex", flexDirection: "column", gap: 1 }}>
          <FormControl sx={{ minWidth: 200 }}>
            <InputLabel id="column-select-label" shrink>
              Visible Columns
            </InputLabel>
            <Select
              labelId="column-select-label"
              multiple
              value={selectedColumns}
              onChange={handleColumnSelectionChange}
              renderValue={(selected) =>
                selected.length === 0 ? (
                  <em style={{ color: "#888" }}>Select columns...</em>
                ) : (
                  selected.join(", ")
                )
              }
              displayEmpty
              label="Visible Columns"
            >
              {columns.map((col) => (
                <MenuItem key={col} value={col}>
                  <Checkbox checked={selectedColumns.indexOf(col) > -1} />
                  <ListItemText primary={col} />
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          {/* Buttons side by side */}
          <Box sx={{ display: "flex", gap: 1 }}>
            <Button variant="outlined" size="small" onClick={toggleSelectAllColumns}>
              {isAllSelected ? "Deselect All" : "Select All"}
            </Button>

            <Button variant="outlined" size="small" onClick={() => setFilterDialogOpen(true)}>
              Add Filter
            </Button>
          </Box>
        </Box>
      )}

      {/* Show applied filters as chips with remove button */}
      {filters.length > 0 && (
        <Stack direction="row" spacing={1} sx={{ mb: 2, flexWrap: "wrap" }}>
          {filters.map(({ column, value }, idx) => (
            <Chip
              key={`${column}-${idx}`}
              label={`${column}: "${value}"`}
              onDelete={() => handleRemoveFilter(idx)}
              color="primary"
              variant="outlined"
            />
          ))}
          <Button
            size="small"
            variant="text"
            color="secondary"
            onClick={() => setFilters([])}
            sx={{ ml: 1 }}
          >
            Clear All Filters
          </Button>
        </Stack>
      )}

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", mt: 2 }}>
          <CircularProgress />
        </Box>
      ) : currentPageRows.length === 0 ? (
        <Typography>No rows to display.</Typography>
      ) : (
        <Box
          sx={{
            maxHeight: 400,
            overflowY: "auto",
            width: "100%",
          }}
        >
          <Table
            size="small"
            sx={{
              width: "100%",
              minWidth: 650,
            }}
          >
            <TableHead>
              <TableRow>
                {selectedColumns.map((col) => (
                  <TableCell
                    key={col}
                    sx={{
                      position: "sticky",
                      top: 0,
                      backgroundColor: "background.paper",
                      zIndex: 1,
                      fontWeight: "bold",
                    }}
                  >
                    {col}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>

            <TableBody>
              {currentPageRows.map((row, idx) => (
                <TableRow key={idx}>
                  {selectedColumns.map((col) => (
                    <TableCell key={col}>
                      {Array.isArray(row[col]) ? (
                        <ExpandableList items={row[col]} maxVisible={3} />
                      ) : typeof row[col] === "object" ? (
                        JSON.stringify(row[col], null, 2)
                      ) : (
                        row[col]?.toString()
                      )}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>

            <TableFooter>
              <TableRow>
                <TablePagination
                  count={filteredRows.length}
                  rowsPerPage={limit}
                  page={Math.floor(offset / limit)}
                  onPageChange={handleChangePage}
                  rowsPerPageOptions={[]}
                  labelDisplayedRows={({ from, to, count }) =>
                    `${from}–${to} of ${count}`
                  }
                  nextIconButtonProps={{
                    disabled: offset + limit >= filteredRows.length,
                  }}
                  backIconButtonProps={{
                    disabled: offset === 0,
                  }}
                />
              </TableRow>
            </TableFooter>
          </Table>
        </Box>
      )}

      {/* Filter Dialog */}
      <Dialog
        open={filterDialogOpen}
        onClose={() => setFilterDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Add Filter</DialogTitle>
        <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
          <FormControl fullWidth>
            <InputLabel id="filter-column-label">Column</InputLabel>
            <Select
              labelId="filter-column-label"
              value={tempFilter.column}
              onChange={(e) =>
                setTempFilter((prev) => ({ ...prev, column: e.target.value }))
              }
            >
              {selectedColumns.map((col) => (
                <MenuItem key={col} value={col}>
                  {col}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <TextField
            label="Value"
            value={tempFilter.value}
            onChange={(e) =>
              setTempFilter((prev) => ({ ...prev, value: e.target.value }))
            }
            fullWidth
          />
        </DialogContent>

        <DialogActions>
          <Button onClick={() => setFilterDialogOpen(false)}>Cancel</Button>
          <Button
            onClick={handleAddFilter}
            variant="contained"
            disabled={!tempFilter.column || !tempFilter.value}
          >
            Add
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
