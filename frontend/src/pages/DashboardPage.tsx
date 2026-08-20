import React from 'react';
import { useNavigate } from 'react-router-dom';
import JobDashboard from '../components/JobDashboard';

export default function DashboardPage() {
  const navigate = useNavigate();

  const handleSelectJob = (jobId: string) => {
    navigate(`/job/${jobId}`);
  };

  return <JobDashboard onSelectJob={handleSelectJob} />;
}
