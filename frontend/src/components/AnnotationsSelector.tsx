/*
 * Copyright 2025-2026 IBM Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

import React from "react";
import { Annotation, ALL_ANNOTATIONS } from "../models/Models";
import { FormGroup, FormControlLabel, Checkbox, Typography } from "@mui/material";

interface Props {
  selected: Annotation[] | undefined;
  disabled?: boolean;
  onChange: (annotation: Annotation, checked: boolean) => void;
}

export default function AnnotationsSelector({ selected = [], disabled, onChange }: Props) {
  return (
    <>
      <Typography variant="subtitle1" gutterBottom sx={{ fontWeight: 'bold' }}>
        Annotations
      </Typography>
      <FormGroup row aria-label="annotations selection" sx={{ gap: 3 }}>
        {ALL_ANNOTATIONS.map((ann) => (
          <FormControlLabel
            key={ann}
            control={
              <Checkbox
                checked={selected.includes(ann)}
                onChange={(e) => onChange(ann, e.target.checked)}
                disabled={disabled}
                inputProps={{ 'aria-label': ann }}
              />
            }
            label={ann}
          />
        ))}
      </FormGroup>
    </>
  );
}
