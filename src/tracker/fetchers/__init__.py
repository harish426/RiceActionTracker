"""Fetching: plain HTTP first, headless browser as a fallback, PDFs to text."""

from tracker.fetchers.base import Fetcher, FetchError, FetchResult
from tracker.fetchers.http import HttpFetcher
from tracker.fetchers.ladder import LadderFetcher

__all__ = ["FetchError", "FetchResult", "Fetcher", "HttpFetcher", "LadderFetcher"]
