"""SRPE portal client: session bootstrap, API calls, and RT PDF download URLs."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
from playwright.sync_api import sync_playwright

API_BASE = "https://www.srpe.gov.hk/api/SrpeWebService"
OPIP_BASE = "https://www.srpe.gov.hk/opip"


@dataclass
class DevelopmentSummary:
  dev_id: str
  eng_phase_name: str | None
  chn_phase_name: str | None
  eng_name: str | None
  chn_name: str | None
  eng_address: str | None
  chn_address: str | None


@dataclass
class RegisterOfTransactionsFile:
  dev_id: str
  file_id: str
  file_name: str
  file_size: int | None
  submission_time: str | None
  download_url: str


class SrpeClient:
  """Minimal SRPE client for the Extract layer."""

  def __init__(
    self,
    *,
    language: str = "en",
    user_agent: str = "SRPE-ETL-Portfolio/0.1 (educational project)",
    timeout_seconds: float = 60.0,
  ) -> None:
    self.language = language
    self.user_agent = user_agent
    self.timeout_seconds = timeout_seconds
    self._action_counter = 0
    self._client = httpx.Client(
      timeout=timeout_seconds,
      follow_redirects=True,
      headers={
        "User-Agent": user_agent,
        "Accept": "application/json, application/pdf, */*",
        "Referer": f"{OPIP_BASE}/dev_bldg_search",
      },
    )

  def close(self) -> None:
    self._client.close()

  def __enter__(self) -> SrpeClient:
    return self

  def __exit__(self, *args: object) -> None:
    self.close()

  def _action_id(self) -> str:
    self._action_counter += 1
    return f"{int(time.time() * 1000)}_{self._action_counter}"

  def _api_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = {
      "language": self.language,
      "actionId": self._action_id(),
      **payload,
    }
    response = self._client.post(f"{API_BASE}/{path}", json=body)
    response.raise_for_status()
    data = response.json()
    if data.get("code") != 0:
      raise RuntimeError(f"SRPE API error for {path}: {data.get('remarks') or data}")
    return data

  def bootstrap_session(self, entry_url: str = f"{OPIP_BASE}/dev_bldg_search") -> None:
    """Open SRPE once in Playwright, accept disclaimer, copy cookies to httpx."""
    with sync_playwright() as playwright:
      browser = playwright.chromium.launch(headless=True)
      context = browser.new_context(user_agent=self.user_agent)
      page = context.new_page()
      page.goto(entry_url, wait_until="networkidle", timeout=120_000)
      page.wait_for_timeout(1500)

      if page.get_by_role("button", name="Continue").count():
        checkbox = page.locator("input[type=checkbox]")
        if checkbox.count():
          checkbox.first.check()
        page.get_by_role("button", name="Continue").click()
        page.wait_for_timeout(1500)

      cookies = context.cookies()
      browser.close()

    self._client.cookies.clear()
    for cookie in cookies:
      self._client.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain"))

  def search_developments_by_name(self, name: str) -> list[DevelopmentSummary]:
    data = self._api_post(
      "DevBldgSearch/getDevBldgSearchResult",
      {
        "timeStamp": int(time.time() * 1000),
        "name": name,
        "dnbnId": name,
        "actionType": "Search Name By Development",
      },
    )
    rows = data.get("resultData", {}).get("list", [])
    results: list[DevelopmentSummary] = []
    for row in rows:
      address = (row.get("addresses") or [{}])[0]
      results.append(
        DevelopmentSummary(
          dev_id=str(row.get("id") or row.get("developmentId")),
          eng_phase_name=row.get("engPhaseName"),
          chn_phase_name=row.get("chnPhaseName"),
          eng_name=row.get("engName"),
          chn_name=row.get("chnName"),
          eng_address=address.get("engAddress"),
          chn_address=address.get("chnAddress"),
        )
      )
    return results

  def get_selected_development(self, dev_id: str) -> dict[str, Any]:
    data = self._api_post(
      "DevBldgSearch/getSelectedDevResult",
      {"devId": str(dev_id)},
    )
    return data.get("resultData") or {}

  def get_register_of_transactions_file(self, dev_id: str) -> RegisterOfTransactionsFile | None:
    detail = self.get_selected_development(dev_id)
    dev_info = detail.get("devInfoResp") or detail
    transactions = dev_info.get("transactions") or []
    if not transactions:
      return None

    latest = max(
      transactions,
      key=lambda item: (item.get("file") or {}).get("submissionTime") or "",
    )
    file_info = latest.get("file") or {}
    file_name = file_info.get("fileName")
    file_id = file_info.get("id")
    if not file_name or not file_id:
      return None

    download_url = self._resolve_download_url(dev_id=dev_id, file_name=file_name)
    return RegisterOfTransactionsFile(
      dev_id=str(dev_id),
      file_id=str(file_id),
      file_name=file_name,
      file_size=file_info.get("fileSize"),
      submission_time=file_info.get("submissionTime"),
      download_url=download_url,
    )

  def _resolve_download_url(self, dev_id: str, file_name: str) -> str:
    """Read the signed RT download URL from the development page."""
    page_url = f"{OPIP_BASE}/selected_dev?devId={dev_id}"
    with sync_playwright() as playwright:
      browser = playwright.chromium.launch(headless=True)
      context = browser.new_context(user_agent=self.user_agent)
      page = context.new_page()

      # Reuse cookies from httpx client if we already bootstrapped.
      if self._client.cookies.jar:
        context.add_cookies(
          [
            {
              "name": cookie.name,
              "value": cookie.value,
              "domain": cookie.domain or "www.srpe.gov.hk",
              "path": cookie.path or "/",
            }
            for cookie in self._client.cookies.jar
          ]
        )

      page.goto(page_url, wait_until="networkidle", timeout=120_000)
      page.wait_for_timeout(1500)

      if page.get_by_role("button", name="Continue").count():
        page.locator("input[type=checkbox]").first.check()
        page.get_by_role("button", name="Continue").click()
        page.wait_for_timeout(1500)

      selector = f"a[href*='{file_name}'], a:has-text('Register of Transactions')"
      link = page.locator(selector).first
      link.wait_for(state="visible", timeout=30_000)
      href = link.get_attribute("href")
      browser.close()

    if not href:
      raise RuntimeError(f"Could not find download link for {file_name} (devId={dev_id})")
    if href.startswith("/"):
      return f"https://www.srpe.gov.hk{href}"
    return href

  def download_register_pdf(self, register_file: RegisterOfTransactionsFile, dest_path) -> None:
    response = self._client.get(register_file.download_url)
    response.raise_for_status()
    if not response.content.startswith(b"%PDF"):
      raise RuntimeError(f"Downloaded file is not a PDF: {register_file.file_name}")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(response.content)
