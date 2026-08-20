import time
import pandas as pd
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from src.processing.text_extraction import download, extract_simple_document


class DocumentDownloader:
    def __init__(self, settings, notify_fn):
        self.settings = settings
        self.notify = notify_fn

    @staticmethod
    def _safe_download(i, link, notify):
        try:
            time.sleep(1)
            content = download(link)
            return i, content, "Success"
        except Exception as e:
            msg = str(e)
            notify(f"Download failed for {link}: {msg}", level="error")
            return i, "", f"Error: {msg}"

    @staticmethod
    def _safe_extract(i, link, content):
        if content is None:
            return i, "", "Success: No content to extract"

        try:
            text = extract_simple_document(content)
            return i, text or "", "Success"
        except Exception as e:
            return i, "", f"Error: {str(e)}"

    def download_and_extract_texts(self, df: pd.DataFrame):
        links = df["link"].fillna("").to_list()
        max_download_workers = self.settings.max_download_workers
        max_extract_workers = self.settings.max_extract_workers

        self.notify("Downloading documents...")
        download_start = time.time()
        contents = [None] * len(links)
        download_status = [""] * len(links)

        with ThreadPoolExecutor(max_workers=max_download_workers) as executor:
            futures = [
                executor.submit(self._safe_download, i, link, self.notify)
                for i, link in enumerate(links)
            ]

            for f in tqdm(as_completed(futures), total=len(futures), desc="Downloading", unit="file"):
                i, content, status = f.result()
                contents[i] = content
                download_status[i] = status

        download_elapsed = time.time() - download_start
        downloaded_count = sum(1 for c in contents if c is not None)
        self.notify(f"{downloaded_count} URLs were downloaded")

        self.notify("Extracting text...")
        extract_start = time.time()
        texts = [None] * len(contents)
        extract_status = [""] * len(contents)

        with ProcessPoolExecutor(max_workers=max_extract_workers) as executor:
            futures = [
                executor.submit(self._safe_extract, i, links[i], contents[i])
                for i in range(len(contents))
            ]

            for f in tqdm(as_completed(futures), total=len(futures), desc="Extracting", unit="file"):
                i, text, status = f.result()
                texts[i] = text
                extract_status[i] = status

        extract_elapsed = time.time() - extract_start
        extracted_count = sum(1 for t in texts if t)

        self.notify(f"{extracted_count} documents were extracted")

        df = df.copy()
        df["extracted_text"] = texts
        df["download_status"] = download_status
        df["extract_status"] = extract_status

        metrics = {
            "downloaded": downloaded_count,
            "extracted": extracted_count,
        }

        timing = {
            "downloading": download_elapsed,
            "extraction": extract_elapsed,
        }

        return df, metrics, timing
