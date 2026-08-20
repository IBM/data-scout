import io
from pypdf import PdfReader
import trafilatura
from curl_cffi import requests
from src.processing.file_ops import get_default_logger


def is_pdf(raw_bytes):
    if not isinstance(raw_bytes, bytes):
        return False
    return raw_bytes.startswith(b'%PDF')


def extract_pdf(raw_byes):
    pdf_stream = io.BytesIO(raw_byes)
    pdf_reader = PdfReader(pdf_stream)

    extracted_pages = []
    for i in range(len(pdf_reader.pages)):
        page = pdf_reader.pages[i]
        extracted_pages.append(page.extract_text())

    return '\n'.join(extracted_pages)


def extract_simple_document(content):
    if is_pdf(content):
        return extract_pdf(content)
    else:
        return trafilatura.extract(content)


MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
DOWNLOAD_TIMEOUT = 30  # seconds


def _is_private_url(url: str) -> bool:
    from urllib.parse import urlparse
    import ipaddress
    hostname = urlparse(url).hostname or ""
    try:
        ip = ipaddress.ip_address(hostname)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return hostname in ("localhost", "")


def download(url):
    logger = get_default_logger()
    try:
        if _is_private_url(url):
            logger.warning(f"Skipping private/local URL: {url}")
            return None
        response = requests.get(
            url,
            impersonate="chrome",
            timeout=DOWNLOAD_TIMEOUT,
            max_recv=MAX_DOWNLOAD_BYTES,
        )
        return response.content
    except Exception as e:
        logger.error(f'Failed to retrieve {url} due to {e}')
        return None
