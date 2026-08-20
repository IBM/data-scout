import argparse
from dotenv import load_dotenv
from src.pipeline.run_wrapper import run_pipeline_from_args_dict

def get_args():
    parser = argparse.ArgumentParser(description="Search Pipeline")

    parser.add_argument("--mode", required=True, choices=["query", "topic", "keyword", "search"],
                        help="Input mode: one of 'query', 'topic', or 'keyword'")

    parser.add_argument("--input", required=True, type=str,
                        help="Input query")
    
    parser.add_argument("--input_file", type=str,
                        help="Option to provide topics.jsonl file to search queries (only valid in 'search' mode)")

    parser.add_argument("--recursion_depth", type=int, default=None,
                        help="How many recursive topic expansions to perform (default: 1, max: 2)")
    
    parser.add_argument("--max_results_per_query", type=int, nargs='?', default=None,
                        help="Max results per query (default: 20, max: 1000)")
    parser.add_argument("--output_format", choices=["jsonl", "parquet"], default=None,
                        help="Output file format (default: jsonl)")
    parser.add_argument("--output_folder_name", type=str, default="searchresults",
                        help="Base name for output file (no extension)")
    parser.add_argument("--annotations",
                        nargs="*",  # Zero or more values allowed
                        choices=["donotcrawl", "relevancy"],
                        default=None,
                        help="Optional annotations to apply. Choices: donotcrawl, relevancy"
                        )
    parser.add_argument("--filter_results",
                        action="store_true",
                        help="If set, only return rows that pass all enabled annotations (default: False)"
                        )
    parser.add_argument('--perform_search',
                        action='store_true',
                        help='If set, pass generated queries to google search to get seeds'
                        )
    
    args = parser.parse_args()

    if args.mode != "search" and args.input_file:
        parser.error("--input_file should only be used when --mode=search")
    
    if args.recursion_depth is not None:
        if args.mode != "topic":
            parser.error("--recursion_depth is only allowed when --mode is 'topic'")
        # Disallow recursion_depth in search mode
        if args.mode == "search":
            parser.error("--recursion_depth is not allowed when --mode is 'search'")


    if not args.perform_search and args.mode != 'search':
        if args.annotations:
            parser.error("--annotations is only allowed when --mode='search' or --perform_search is set")
        if args.filter_results:
            parser.error("--filter_results is only allowed when --mode='search' or --perform_search is set")
        if args.max_results_per_query is not None:
            parser.error("--max_results_per_query is only allowed when --mode='search' or --perform_search is set")

    return args

def get_user_args_dict(args):
    user_args = {
        "mode": args.mode,
        "input": args.input,
        "filter_results": args.filter_results,
        "perform_search": args.perform_search,
    }

    if args.recursion_depth is not None:
        user_args["recursion_depth"] = args.recursion_depth
    if args.max_results_per_query is not None:
        user_args["max_results_per_query"] = args.max_results_per_query
    if args.output_format is not None:
        user_args["output_format"] = args.output_format
    if args.output_folder_name is not None:
        user_args["output_folder_name"] = args.output_folder_name
    if args.annotations is not None:
        user_args["annotations"] = args.annotations
    if args.input_file is not None:
        user_args["input_file"] = args.input_file

    return user_args

def main():
    load_dotenv()
    args = get_args()
    user_args = get_user_args_dict(args)
    run_pipeline_from_args_dict(user_args)

if __name__ == "__main__":
    main()