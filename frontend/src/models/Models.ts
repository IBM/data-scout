export type Mode = "query" | "topic" | "keyword" | "search";
export type OutputFormat = "jsonl" | "parquet";
export type Annotation = "donotcrawl" | "relevancy";

export interface JobSummary {
  job_id: string;
  mode: string;
  input: string;
  // Null until the pipeline records a status; the list endpoint returns the
  // job as soon as its args are stored.
  status: string | null;
  progress?: string | null;
  created_at?: string;
  error?: string | null;
}

export interface JobDetails {
  output_folder_name: string;
  progress: string;
  progress_updated_at: string;  // ISO date string
  input: string;
  status_updated_at: string;    // ISO date string
  status: string;
  mode: string;
  annotations: string;          // looks like a stringified list, you could parse it if needed
  storage_logs_path: string;
  filter_results: string;       // looks like a boolean as a string, e.g. "False"
  task_id: string;
  storage_upload_folder: string;
  output_format: string;
  perform_search: string;       // boolean as string
  max_results_per_query: string; // number as string
  created_at: string;           // ISO date string
  recursion_depth: string;      // number as string
}

export interface UserArgs {
  mode: Mode;
  input: string;
  output_folder_name?: string;
  recursion_depth?: number;
  max_results_per_query?: number;
  output_format?: OutputFormat;
  perform_search: boolean;
  annotations?: Annotation[];
  filter_results?: boolean;
}

export const defaultUserArgs: UserArgs = {
  mode: "query",
  input: "",
  output_folder_name: "searchresults",
  recursion_depth: 1,
  max_results_per_query: 20,
  output_format: "jsonl",
  perform_search: false,
  annotations: ["donotcrawl", "relevancy"],
  filter_results: false,
};

export const ALL_ANNOTATIONS: Annotation[] = ["donotcrawl", "relevancy"];

export const METRIC_CATEGORIES = {
  initialQueryMetrics: [
    "topics_after_recursion_1",
    "initial_keyword_generation",
    "generated_queries",
  ],
  searchResultMetrics: [
    "raw_results",
    "deduped_results",
    "downloaded",
    "extracted",
    "relevant_results",
    "crawlable_results",
    "relevant_and_crawlable",
    "after_filtering",
    "top_10_domains",
  ],
  overallRunTimestamps: [
    "start_timestamp",
    "end_timestamp",
    "elapsed_times"
  ],
};
