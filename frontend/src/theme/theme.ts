/*
 * Copyright 2025-2026 IBM Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

// src/theme/theme.ts
import { createTheme } from "@mui/material/styles";
import { red, blueGrey, teal } from "@mui/material/colors";

export const theme = createTheme({
  palette: {
    primary: {
      main: teal[600], // Custom primary color
    },
    secondary: {
      main: blueGrey[500],
    },
    error: {
      main: red.A400,
    },
    background: {
      default: "#f5f7fa", // Light background
    },
  },
  typography: {
    fontFamily: `"Inter", "Roboto", "Helvetica", "Arial", sans-serif`,
    fontWeightLight: 300,
    fontWeightRegular: 400,
    fontWeightMedium: 600,
    h4: {
      fontWeight: 600,
    },
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 6,
          textTransform: "none",
        },
      },
    },
    MuiTextField: {
      defaultProps: {
        variant: "outlined",
        size: "small",
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          padding: "1.5rem",
        },
      },
    },
  },
});
