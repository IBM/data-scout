/*
 * Copyright 2025-2026 IBM Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

import React from "react";
import { TextField } from "@mui/material";

interface Props {
  value: number | undefined;
  disabled?: boolean;
  onChange: (value: number) => void;
}

const RecursionDepthInput: React.FC<Props> = ({ value, disabled, onChange }) => {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    let newValue = Number(e.target.value);
    if (newValue > 2) newValue = 2;
    if (newValue < 1) newValue = 1;
    onChange(newValue);
  };

  return (
    <TextField
      label="Recursion Depth"
      type="number"
      value={value ?? ""}
      onChange={handleChange}
      inputProps={{ min: 1, max: 2 }}
      disabled={disabled}
      fullWidth
      sx={{ maxWidth: 200 }}
    />
  );
};

export default RecursionDepthInput;
