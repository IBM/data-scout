# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

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
DOWNLOAD_CHUNK_BYTES = 64 * 1024


def _is_private_ip(hostname: str) -> bool:
    import socket
    import ipaddress
    if hostname in ("localhost", ""):
        return True
    try:
        for info in socket.getaddrinfo(hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return True
    except (socket.gaierror, ValueError):
        pass
    return False


def download(url):
    logger = get_default_logger()
    try:
        from urllib.parse import urlparse
        hostname = urlparse(url).hostname or ""
        if _is_private_ip(hostname):
            logger.warning(f"Skipping private/local URL: {url}")
            return None
        # stream=True so the cap is enforced while reading rather than after.
        # `response.content` materialises the whole body first, so the previous
        # check discarded an oversized response only once it was already in
        # memory -- with MAX_DOWNLOAD_WORKERS fetching in parallel, one huge PDF
        # in a result set was enough to exhaust it.
        response = requests.get(
            url,
            impersonate="chrome",
            timeout=DOWNLOAD_TIMEOUT,
            allow_redirects=True,
            stream=True,
        )
        try:
            # The redirect check moves ahead of the body: headers and the final
            # URL are available before any content is read.
            final_host = urlparse(str(response.url)).hostname or ""
            if _is_private_ip(final_host):
                logger.warning(f"Redirect to private IP blocked: {url} -> {response.url}")
                return None

            # Advisory only -- servers may omit or understate it, so it is an
            # early exit, never the sole guard.
            declared = response.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > MAX_DOWNLOAD_BYTES:
                logger.warning(f"Response too large (Content-Length {declared} bytes): {url}")
                return None

            chunks = []
            total = 0
            for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_BYTES):
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    logger.warning(
                        f"Response too large (exceeded {MAX_DOWNLOAD_BYTES} bytes): {url}"
                    )
                    return None
                chunks.append(chunk)

            return b"".join(chunks)
        finally:
            response.close()
    except Exception as e:
        logger.error(f'Failed to retrieve {url} due to {e}')
        return None
