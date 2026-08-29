/*
 * Copyright 2025-2026 IBM Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

import { defaultUserArgs, ALL_ANNOTATIONS, METRIC_CATEGORIES } from "./Models";

describe("Models", () => {
  describe("defaultUserArgs", () => {
    it("has query mode by default", () => {
      expect(defaultUserArgs.mode).toBe("query");
    });

    it("has empty input", () => {
      expect(defaultUserArgs.input).toBe("");
    });

    it("has perform_search disabled", () => {
      expect(defaultUserArgs.perform_search).toBe(false);
    });

    it("has both annotations enabled by default", () => {
      expect(defaultUserArgs.annotations).toEqual(["donotcrawl", "relevancy"]);
    });

    it("has default output folder name", () => {
      expect(defaultUserArgs.output_folder_name).toBe("searchresults");
    });

    it("has default recursion depth of 1", () => {
      expect(defaultUserArgs.recursion_depth).toBe(1);
    });

    it("has default max results per query of 20", () => {
      expect(defaultUserArgs.max_results_per_query).toBe(20);
    });

    it("defaults to jsonl output format", () => {
      expect(defaultUserArgs.output_format).toBe("jsonl");
    });

    it("has filter_results disabled", () => {
      expect(defaultUserArgs.filter_results).toBe(false);
    });
  });

  describe("ALL_ANNOTATIONS", () => {
    it("contains donotcrawl and relevancy", () => {
      expect(ALL_ANNOTATIONS).toEqual(["donotcrawl", "relevancy"]);
    });
  });

  describe("METRIC_CATEGORIES", () => {
    it("has initialQueryMetrics category", () => {
      expect(METRIC_CATEGORIES.initialQueryMetrics).toContain("generated_queries");
    });

    it("has searchResultMetrics category", () => {
      expect(METRIC_CATEGORIES.searchResultMetrics).toContain("raw_results");
      expect(METRIC_CATEGORIES.searchResultMetrics).toContain("relevant_results");
    });

    it("has overallRunTimestamps category", () => {
      expect(METRIC_CATEGORIES.overallRunTimestamps).toContain("start_timestamp");
      expect(METRIC_CATEGORIES.overallRunTimestamps).toContain("end_timestamp");
    });
  });
});
