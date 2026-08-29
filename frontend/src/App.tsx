/*
 * Copyright 2025-2026 IBM Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { BrowserRouter as Router, Routes, Route, useNavigate, Navigate } from 'react-router-dom';
import {
  CssBaseline,
  Container,
  AppBar,
  Toolbar,
  Typography,
  Button,
  Box
} from '@mui/material';
import JobForm from './components/JobForm';
import DashboardPage from './pages/DashboardPage';
import JobDetailPage from './pages/JobDetailPage';
import JobDetail from './components/JobDetail';
import ExploreIcon from '@mui/icons-material/Explore';
import AddCircleOutlineIcon from '@mui/icons-material/AddCircleOutline';

function App() {
  return (
    <Router>
      <CssBaseline />
      <AppLayout />
    </Router>
  );
}

// Layout with top bar and routing
function AppLayout() {
  const navigate = useNavigate();

  // This handles job row clicks by navigating to job detail page
  function handleSelectJob(jobId: string) {
    navigate(`/job/${jobId}`);
  }

  return (
    <>
      <AppBar position="static" sx={{ backgroundColor: '#149d81ff' }}>
        <Toolbar>
          <Typography
            component="div"
            sx={{
              flexGrow: 1,
              fontWeight: 700,
              fontSize: '1.75rem', // Bigger than default h5
              letterSpacing: 1,
              display: 'flex',
              alignItems: 'center',
              gap: 1.5,
              cursor: 'pointer',
              userSelect: 'none',
              fontFamily: 'Montserrat, Roboto, sans-serif',
            }}
            onClick={() => navigate('/dashboard')}
          >
            <ExploreIcon sx={{ fontSize: '2rem' }} /> {/* Make icon larger */}
            Data Scout
          </Typography>
          <Button 
            variant="contained"
            sx={{ 
              backgroundColor: '#1976d2', 
              color: '#fff', 
              '&:hover': { backgroundColor: '#115293' },
              fontWeight: 600,
              textTransform: 'none'
            }}
            onClick={() => navigate('/submit')}
          >
            + Create New Job
          </Button>
        </Toolbar>
      </AppBar>

      <Box sx={{ paddingTop: 4 }}>
        <Container maxWidth="lg">
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/submit" element={<JobForm />} />
            <Route path="/job/:jobId" element={<JobDetailPage />} />
          </Routes>
        </Container>
      </Box>
    </>
  );
}

export default App;
