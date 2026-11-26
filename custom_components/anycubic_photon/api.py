"""Client for the Anycubic Photon local LAN protocol (TCP port 6000).

The protocol is plain text: the client opens a TCP connection, sends a
command such as ``getstatus,end``, and the printer answers with a
comma-separated line that also ends in ``,end``. A new connection is used for
every command, which is how Anycubic's own tools behave.

This module has no Home Assistant dependency, so it can also be run on its own
to check whether a printer speaks the protocol:

    python api.py 192.168.1.50
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import re
import sys

DEFAULT_PORT = 6000
TERMINATOR = ",end"
CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 10.0


class PhotonError(Exception):
    """Base error for the Photon client."""


class PhotonConnectionError(PhotonError):
    """The printer could not be reached or did not answer."""


class PhotonResponseError(PhotonError):
    """The printer answered with something we could not understand."""


@dataclass
class PhotonSysInfo:
    """Answer to ``sysinfo``."""

    model: str
    firmware: str
    serial: str
    wifi: str | None = None


@dataclass
class PhotonStatus:
    """Answer to ``getstatus``.

    Only ``state`` is guaranteed. The printer sends fewer fields when it is
    idle, so everything else may be ``None``.
    """

    state: str
    file_name: str | None = None
    internal_file: str | None = None
    total_layers: int | None = None
    progress: int | None = None
    current_layer: int | None = None
    elapsed_seconds: int | None = None
    remaining_seconds: int | None = None
    resin_ml: float | None = None
    mode: str | None = None
    layer_height_mm: float | None = None
    raw: list[str] = field(default_factory=list)

    @property
    def is_printing(self) -> bool:
        return self.state == "print"

    @property
    def is_paused(self) -> bool:
        return self.state.startswith("paus")


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value.strip()))
    except ValueError:
        return None


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    return float(match.group()) if match else None


def _field(fields: list[str], index: int) -> str | None:
    if index < len(fields):
        value = fields[index].strip()
        return value or None
    return None


def _decode(data: bytes) -> str:
    # Most firmware answers in UTF-8; some older builds use GBK for file names.
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("gbk", errors="replace")


def _split_reply(command: str, reply: str) -> list[str]:
    """Strip the terminator and the echoed command name from a reply."""
    reply = reply.strip()
    if reply.endswith(TERMINATOR):
        reply = reply[: -len(TERMINATOR)]
    fields = [part.strip() for part in reply.split(",")]
    if not fields or fields[0].lower() != command.lower():
        raise PhotonResponseError(f"Unexpected reply to {command!r}: {reply!r}")
    return fields[1:]


def parse_sysinfo(reply: str) -> PhotonSysInfo:
    """Parse e.g. ``sysinfo,Photon Mono X 6K,V0.2.2,0000170300020034,MyWifi,end``."""
    fields = _split_reply("sysinfo", reply)
    if len(fields) < 3:
        raise PhotonResponseError(f"sysinfo reply too short: {reply!r}")
    return PhotonSysInfo(
        model=fields[0],
        firmware=fields[1],
        serial=fields[2],
        wifi=_field(fields, 3),
    )


def parse_status(reply: str) -> PhotonStatus:
    """Parse a ``getstatus`` reply.

    Example while printing::

        getstatus,print,Widget.pwmb/46.pwmb,2338,88,2062,51744,6844,~178mL,UV,39.38,0.05,0,end

    Field order: state, file (display/internal), total layers, percent,
    current layer, elapsed s, remaining s, resin volume, mode, ?, layer
    height, ?.
    """
    fields = _split_reply("getstatus", reply)
    if not fields or not fields[0]:
        raise PhotonResponseError(f"getstatus reply has no state: {reply!r}")

    file_field = _field(fields, 1)
    file_name = internal = None
    if file_field:
        file_name, _, internal = file_field.partition("/")
        internal = internal or None

    return PhotonStatus(
        state=fields[0].lower(),
        file_name=file_name,
        internal_file=internal,
        total_layers=_to_int(_field(fields, 2)),
        progress=_to_int(_field(fields, 3)),
        current_layer=_to_int(_field(fields, 4)),
        elapsed_seconds=_to_int(_field(fields, 5)),
        remaining_seconds=_to_int(_field(fields, 6)),
        resin_ml=_to_float(_field(fields, 7)),
        mode=_field(fields, 8),
        layer_height_mm=_to_float(_field(fields, 10)),
        raw=fields,
    )


class PhotonClient:
    """Async client for one printer."""

    def __init__(self, host: str, port: int = DEFAULT_PORT) -> None:
        self.host = host
        self.port = port
        # The printer firmware handles one client at a time.
        self._lock = asyncio.Lock()

    async def send(self, command: str) -> str:
        """Send one command and return the raw reply text."""
        message = command if command.endswith(TERMINATOR) else command + TERMINATOR
        async with self._lock:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), CONNECT_TIMEOUT
                )
            except (OSError, asyncio.TimeoutError) as err:
                raise PhotonConnectionError(
                    f"Cannot connect to {self.host}:{self.port}: {err}"
                ) from err

            try:
                writer.write(message.encode("utf-8"))
                await writer.drain()
                data = await asyncio.wait_for(self._read_reply(reader), READ_TIMEOUT)
            except (OSError, asyncio.TimeoutError) as err:
                raise PhotonConnectionError(
                    f"No reply to {command!r} from {self.host}:{self.port}"
                ) from err
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass

        return _decode(data)

    @staticmethod
    async def _read_reply(reader: asyncio.StreamReader) -> bytes:
        buffer = b""
        end = TERMINATOR.encode()
        while not buffer.rstrip().endswith(end):
            chunk = await reader.read(1024)
            if not chunk:
                break
            buffer += chunk
        if not buffer:
            raise PhotonConnectionError("Printer closed the connection without replying")
        return buffer

    async def get_sysinfo(self) -> PhotonSysInfo:
        return parse_sysinfo(await self.send("sysinfo"))

    async def get_status(self) -> PhotonStatus:
        return parse_status(await self.send("getstatus"))

    async def pause(self) -> None:
        await self.send("gopause")

    async def resume(self) -> None:
        await self.send("goresume")

    async def stop(self) -> None:
        await self.send("gostop")


async def _probe(host: str, port: int) -> int:
    client = PhotonClient(host, port)
    for command in ("sysinfo", "getstatus", "getwifi"):
        try:
            reply = await client.send(command)
        except PhotonError as err:
            print(f"{command}: FAILED - {err}")
            return 1
        print(f"{command}: {reply.strip()}")
    print("\nThe printer speaks the port-6000 protocol; the integration will work.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python api.py <printer-ip> [port]")
        sys.exit(2)
    sys.exit(
        asyncio.run(
            _probe(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT)
        )
    )
