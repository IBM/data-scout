RECURSION_DEPTH_LIMIT=2
MAX_RESULTS_PER_QUERY_LIMIT=1000
MAX_GOOGLE_API_HITS_PER_JOB=2000
# Tavily's own per-request ceiling. Requests above it are capped by the API, so
# the client reports the cap rather than silently swallowing the difference.
TAVILY_MAX_RESULTS_PER_QUERY=20
