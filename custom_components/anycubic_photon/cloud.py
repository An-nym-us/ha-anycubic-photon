"""Client for Anycubic Cloud (the service behind the Anycubic app and Slicer Next).

Anycubic does not publish this API. The endpoints, request signing and
field names below come from community reverse engineering, so Anycubic can
change them without notice.

Two ways to authenticate are supported:

* ``slicer``: the login token Anycubic Slicer Next gets when you sign in.
  Slicer Next 2.x writes it to its debug log as ``id_token=...`` (valid for
  about 90 days); older versions stored it as ``access_token`` in
  ``%AppData%\\AnycubicSlicerNext\\AnycubicSlicerNext.conf``. It is exchanged
  for a session token on every start-up.
* ``web``: the ``XX-Token`` value from cloud-universe.anycubic.com's local
  storage. Simpler to get, but it expires and then needs re-entering.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any
import uuid

import aiohttp

from .api import PhotonAuthError, PhotonConnectionError, PhotonError, PhotonStatus, PhotonSysInfo

BASE_URL = "https://cloud-universe.anycubic.com/p/p/workbench/api"
APP_ID = "f9b3528877c94d5c9c5af32245db46ef"
APP_SECRET = "0cf75926606049a3937f56b0373b99fb"

AUTH_SLICER = "slicer"
AUTH_WEB = "web"

_MODE_HEADERS = {
    AUTH_SLICER: {"device_type": "pcf", "version": "V3.0.0", "is_cn": "1"},
    AUTH_WEB: {"device_type": "web", "version": "1.0.0", "is_cn": "1"},
}
# Anycubic answers HTTP 403 to requests without a browser-like User-Agent.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
_WEB_EXTRA_HEADERS = {"Origin": "https://uc.makeronline.com"}

# Values of a project's ``print_status``.
_PRINT_STATUS = {
    1: "printing",
    2: "finished",
    3: "cancelled",
    4: "downloading",
    5: "checking",
    6: "preheating",
    7: "slicing",
}
_ACTIVE_STATES = {"printing", "paused", "downloading", "checking", "preheating"}

ORDER_PAUSE = 2
ORDER_RESUME = 3
ORDER_STOP = 4

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)


def _to_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _as_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip().startswith("{"):
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _firmware(printer: dict) -> str:
    version = printer.get("version")
    if isinstance(version, dict):
        for key in ("firmware_version", "version", "firmware"):
            if version.get(key):
                return str(version[key])
    elif version:
        return str(version)
    return "unknown"


def parse_cloud_status(printer: dict, project: dict | None) -> PhotonStatus:
    """Turn a printer entry plus its latest project into a PhotonStatus."""
    raw = [f"device_status={printer.get('device_status')}", f"is_printing={printer.get('is_printing')}"]

    if _to_int(printer.get("device_status")) not in (None, 1):
        return PhotonStatus(state="offline", raw=raw)

    # The printer's own busy flag (2 = busy). Prints started at the printer,
    # for example from USB, may have no cloud project to read details from.
    busy = _to_int(printer.get("is_printing")) == 2

    if not project:
        return PhotonStatus(state="printing" if busy else "idle", raw=raw)

    print_status = _to_int(project.get("print_status"))
    state = _PRINT_STATUS.get(print_status, "unknown")
    if state == "printing" and _to_int(project.get("pause")):
        state = "paused"
    raw.append(f"print_status={print_status}")

    if state not in _ACTIVE_STATES:
        if busy:
            # The latest cloud job is over, but the printer is working on
            # something the cloud has no details for.
            return PhotonStatus(state="printing", raw=raw)
        # The job is over; report the outcome without stale job numbers.
        return PhotonStatus(state=state, file_name=_file_name(project), raw=raw)

    settings = _as_dict(project.get("settings"))
    elapsed = _to_int(project.get("print_time"))
    remaining = _to_int(project.get("remain_time"))
    return PhotonStatus(
        state=state,
        file_name=_file_name(project),
        internal_file=str(project.get("id")),
        total_layers=_to_int(settings.get("total_layers")),
        progress=_to_int(project.get("progress")),
        current_layer=_to_int(settings.get("curr_layer")),
        # The cloud reports minutes.
        elapsed_seconds=elapsed * 60 if elapsed is not None else None,
        remaining_seconds=remaining * 60 if remaining is not None else None,
        raw=raw,
    )


def _file_name(project: dict) -> str | None:
    name = project.get("gcode_name") or project.get("name")
    return str(name) if name else None


class AnycubicCloudClient:
    """Signed HTTP client for one Anycubic account."""

    def __init__(self, session: aiohttp.ClientSession, auth_mode: str, token: str) -> None:
        if auth_mode not in _MODE_HEADERS:
            raise ValueError(f"Unknown auth mode {auth_mode!r}")
        self._session = session
        self._mode = auth_mode
        self._token = token.strip().strip('"').removeprefix("id_token=")
        self._session_token: str | None = self._token if auth_mode == AUTH_WEB else None

    def _headers(self, with_token: bool) -> dict[str, str]:
        mode = _MODE_HEADERS[self._mode]
        nonce = str(uuid.uuid1())
        timestamp = str(int(time.time() * 1000))
        signature = hashlib.md5(
            f"{APP_ID}{timestamp}{mode['version']}{APP_SECRET}{nonce}{APP_ID}".encode()
        ).hexdigest()
        headers = {
            "XX-Device-Type": mode["device_type"],
            "XX-Is-Cn": mode["is_cn"],
            "XX-Nonce": nonce,
            "XX-Signature": signature,
            "XX-Timestamp": timestamp,
            "XX-Version": mode["version"],
            "XX-LANGUAGE": "US",
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
        }
        if self._mode == AUTH_WEB:
            headers.update(_WEB_EXTRA_HEADERS)
        if with_token and self._session_token:
            headers["XX-Token"] = self._session_token
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        body: dict | None = None,
        with_token: bool = True,
    ) -> dict:
        try:
            async with self._session.request(
                method,
                BASE_URL + path,
                params=params,
                data=json.dumps(body) if body is not None else None,
                headers=self._headers(with_token),
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status in (401, 403):
                    raise PhotonAuthError(f"Anycubic Cloud refused the token (HTTP {resp.status})")
                payload = await resp.json(content_type=None)
        except PhotonError:
            raise
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise PhotonConnectionError(f"Anycubic Cloud request failed: {err}") from err

        if not isinstance(payload, dict):
            raise PhotonConnectionError("Anycubic Cloud returned an unexpected response")
        return payload

    async def login(self) -> None:
        """Get a session token and confirm it works."""
        if self._mode == AUTH_SLICER:
            payload = await self._request(
                "POST",
                "/v3/public/loginWithAccessToken",
                body={"device_type": "pcf", "access_token": self._token},
                with_token=False,
            )
            token = (payload.get("data") or {}).get("token")
            if not token:
                raise PhotonAuthError(
                    f"Anycubic Cloud rejected the Slicer Next token: {payload.get('msg')}"
                )
            self._session_token = token

        payload = await self._request("GET", "/user/profile/userInfo")
        if not payload.get("data"):
            raise PhotonAuthError(f"Anycubic Cloud token is invalid or expired: {payload.get('msg')}")

    async def _get_data(self, path: str, params: dict | None = None) -> Any:
        """GET and return ``data``, logging in again once if the session lapsed."""
        for attempt in (1, 2):
            if self._session_token is None:
                await self.login()
            payload = await self._request("GET", path, params=params)
            if payload.get("data") is not None:
                return payload["data"]
            if attempt == 1 and self._mode == AUTH_SLICER:
                self._session_token = None  # re-exchange the access token
                continue
            # A web token can't be refreshed; check whether it's the cause.
            check = await self._request("GET", "/user/profile/userInfo")
            if not check.get("data"):
                raise PhotonAuthError("Anycubic Cloud token is invalid or expired")
            raise PhotonConnectionError(f"Anycubic Cloud error on {path}: {payload.get('msg')}")
        raise PhotonConnectionError(f"Anycubic Cloud error on {path}")

    async def list_printers(self) -> list[dict]:
        data = await self._get_data("/work/printer/getPrinters")
        return data if isinstance(data, list) else []

    async def latest_project(self, printer_id: int) -> dict | None:
        data = await self._get_data("/work/project/getProjects", {"page": 1, "limit": 20})
        projects = data if isinstance(data, list) else (data or {}).get("list", [])
        for project in projects:
            if _to_int(project.get("printer_id")) == printer_id:
                return project
        return None

    async def send_order(self, order_id: int, printer_id: int, project_id: int) -> None:
        if self._session_token is None:
            await self.login()
        payload = await self._request(
            "POST",
            "/work/operation/sendOrder",
            body={
                "order_id": order_id,
                "printer_id": printer_id,
                "project_id": project_id,
                "data": None,
                "ams_info": None,
                "settings": None,
            },
        )
        if not payload.get("data"):
            raise PhotonError(
                f"Anycubic Cloud did not accept the command (is the printer online?): {payload.get('msg')}"
            )


class CloudPrinter:
    """One printer on an Anycubic account, with the same methods as PhotonClient."""

    def __init__(self, client: AnycubicCloudClient, printer_id: int) -> None:
        self._client = client
        self.printer_id = printer_id
        self._project_id: int | None = None

    async def get_sysinfo(self) -> PhotonSysInfo:
        printer = await self._find_printer()
        return PhotonSysInfo(
            model=str(printer.get("model") or printer.get("machine_type") or "Anycubic printer"),
            firmware=_firmware(printer),
            serial=f"cloud_{self.printer_id}",
            name=printer.get("name"),
        )

    async def get_status(self) -> PhotonStatus:
        printer = await self._find_printer()
        project = await self._client.latest_project(self.printer_id)
        status = parse_cloud_status(printer, project)
        active = status.state in _ACTIVE_STATES
        self._project_id = _to_int(project.get("id")) if project and active else None
        return status

    async def _find_printer(self) -> dict:
        for printer in await self._client.list_printers():
            if _to_int(printer.get("id")) == self.printer_id:
                return printer
        raise PhotonConnectionError(
            f"Printer {self.printer_id} is no longer on this Anycubic account"
        )

    async def _order(self, order_id: int) -> None:
        if self._project_id is None:
            raise PhotonError("No print is running")
        await self._client.send_order(order_id, self.printer_id, self._project_id)

    async def pause(self) -> None:
        await self._order(ORDER_PAUSE)

    async def resume(self) -> None:
        await self._order(ORDER_RESUME)

    async def stop(self) -> None:
        await self._order(ORDER_STOP)
