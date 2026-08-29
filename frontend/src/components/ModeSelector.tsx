/*
 * Copyright 2025-2026 IBM Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

import React from "react";
import { FormControl, InputLabel, Select, MenuItem } from "@mui/material";
import { Mode } from "../models/Models";

interface Props {
  value: Mode;
  disabled?: boolean;
  onChange: (mode: Mode) => void;
}

const ModeSelector: React.FC<Props> = ({ value, disabled, onChange }) => {
  return (
    <FormControl fullWidth disabled={disabled} sx={{ mb: 2 }}>
      <InputLabel id="mode-select-label">Mode</InputLabel>
      <Select
        labelId="mode-select-label"
        value={value}
        label="Mode"
        onChange={(e) => onChange(e.target.value as Mode)}
      >
        <MenuItem value="query">query</MenuItem>
        <MenuItem value="topic">topic</MenuItem>
        <MenuItem value="keyword">keyword</MenuItem>
        <MenuItem value="search">search</MenuItem>
      </Select>
    </FormControl>
  );
};

export default ModeSelector;
