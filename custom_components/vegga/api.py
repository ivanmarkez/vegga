from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession

from .const import API_BASE_URL, CLIENT_ID, CORE_BASE_URL, HISTORY_BASE_URL, LOGIN_URL, OAUTH_SCOPE

_LOGGER = logging.getLogger(__name__)


class VeggaApiError(Exception):
    """Base VEGGA API error."""


class VeggaAuthError(VeggaApiError):
    """Authentication error."""


class VeggaApi:
    """Async client for VEGGA with automatic token management."""

    def __init__(
        self,
        session: ClientSession,
        username: str,
        password: str,
        device_id: str | None = None,
    ) -> None:
        self._session = session
        self._username = username.strip()
        self._password = password
        self.device_id = str(device_id).strip() if device_id is not None else ""
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at: datetime | None = None
        self._auth_lock = asyncio.Lock()
        self.history_debug: dict[str, Any] = {}

    @property
    def headers(self) -> dict[str, str]:
        if not self._access_token:
            raise VeggaAuthError("No hay una sesión VEGGA activa")
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
        }

    def _token_is_valid(self) -> bool:
        return bool(
            self._access_token
            and self._expires_at
            and datetime.now(timezone.utc) < self._expires_at - timedelta(seconds=90)
        )

    async def async_login(self) -> None:
        """Log in using the password grant observed in the VEGGA web app."""
        await self._authenticate(
            {
                "username": self._username,
                "password": self._password,
                "grant_type": "password",
                "scope": OAUTH_SCOPE,
                "client_id": CLIENT_ID,
                "response_type": "token",
            }
        )

    async def async_refresh_token(self) -> None:
        """Try the standard OAuth refresh grant.

        If VEGGA does not accept it, async_ensure_authenticated falls back to a
        fresh username/password login, so the integration remains operational.
        """
        if not self._refresh_token:
            raise VeggaAuthError("VEGGA no devolvió refresh_token")
        await self._authenticate(
            {
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "scope": OAUTH_SCOPE,
                "client_id": CLIENT_ID,
            }
        )

    async def _authenticate(self, data: dict[str, str]) -> None:
        try:
            _LOGGER.debug("VEGGA login request to %s using grant_type=%s", LOGIN_URL, data.get("grant_type"))
            async with self._session.post(
                LOGIN_URL,
                data=data,
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=20,
            ) as response:
                body = await response.text()
                _LOGGER.debug("VEGGA login response status=%s body=%s", response.status, body[:1000])
                if response.status in (400, 401, 403):
                    raise VeggaAuthError(f"Login rechazado por VEGGA (HTTP {response.status}): {body[:300]}")
                response.raise_for_status()
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError as err:
                    raise VeggaApiError(f"Respuesta de login no válida (HTTP {response.status}): {body[:300]}") from err
        except VeggaAuthError:
            raise
        except (ClientError, ValueError, TimeoutError) as err:
            raise VeggaApiError(f"No se pudo iniciar sesión en VEGGA: {err}") from err

        access_token = payload.get("access_token")
        if not access_token:
            raise VeggaAuthError("VEGGA no devolvió access_token")

        self._access_token = str(access_token)
        if payload.get("refresh_token"):
            self._refresh_token = str(payload["refresh_token"])
        try:
            expires_in = int(payload.get("expires_in", 7200))
        except (TypeError, ValueError):
            expires_in = 7200
        self._expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    async def async_ensure_authenticated(self, *, force: bool = False) -> None:
        if not force and self._token_is_valid():
            return
        async with self._auth_lock:
            if not force and self._token_is_valid():
                return
            if self._refresh_token:
                try:
                    await self.async_refresh_token()
                    return
                except VeggaApiError:
                    self._access_token = None
                    self._refresh_token = None
                    self._expires_at = None
            await self.async_login()

    async def _request_url(
        self,
        method: str,
        url: str,
        *,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        retry_auth: bool = True,
    ) -> Any:
        await self.async_ensure_authenticated()
        try:
            _LOGGER.debug("VEGGA API request %s %s", method, url)
            async with self._session.request(
                method,
                url,
                headers=self.headers,
                json=json_data,
                params=params,
                timeout=30,
            ) as response:
                _LOGGER.debug("VEGGA API response %s %s -> HTTP %s", method, url, response.status)
                if response.status in (401, 403):
                    if retry_auth:
                        await self.async_ensure_authenticated(force=True)
                        return await self._request_url(
                            method,
                            url,
                            json_data=json_data,
                            params=params,
                            retry_auth=False,
                        )
                    raise VeggaAuthError("La sesión de VEGGA ha caducado")
                response.raise_for_status()
                if response.status == 204:
                    return None
                return await response.json(content_type=None)
        except VeggaAuthError:
            raise
        except ClientResponseError as err:
            raise VeggaApiError(f"Error HTTP {err.status} en {url}") from err
        except (ClientError, ValueError, TimeoutError) as err:
            raise VeggaApiError(str(err)) from err

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_data: dict[str, Any] | None = None,
    ) -> Any:
        return await self._request_url(
            method, f"{API_BASE_URL}{path}", json_data=json_data
        )

    @staticmethod
    def _extract_list(data: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in keys:
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def _find_user_id(data: Any) -> str | None:
        """Find a numeric VEGGA user ID in a profile response."""
        preferred = ("userId", "user_id", "idUser", "id_user", "id")
        if isinstance(data, dict):
            for key in preferred:
                value = data.get(key)
                if isinstance(value, int) or (
                    isinstance(value, str) and value.strip().isdigit()
                ):
                    return str(value).strip()
            for value in data.values():
                found = VeggaApi._find_user_id(value)
                if found:
                    return found
        elif isinstance(data, list):
            for value in data:
                found = VeggaApi._find_user_id(value)
                if found:
                    return found
        return None

    def _user_id_from_token(self) -> str | None:
        """Read common user-id claims from the JWT without validating it.

        The token itself has already been obtained over HTTPS from VEGGA. This
        decoding is only used to locate a claim, not to authenticate requests.
        """
        if not self._access_token:
            return None
        parts = self._access_token.split(".")
        if len(parts) < 2:
            return None
        try:
            raw = parts[1] + "=" * (-len(parts[1]) % 4)
            claims = json.loads(base64.urlsafe_b64decode(raw).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        for key in ("userId", "user_id", "idUser", "id_user", "uid", "sub"):
            value = claims.get(key)
            if isinstance(value, int) or (
                isinstance(value, str) and value.strip().isdigit()
            ):
                return str(value).strip()
        return None

    async def get_units(self) -> list[dict[str, Any]]:
        """Return controllers linked to the logged-in account.

        VEGGA's CORE profile returns the organization id (671), while the
        legacy Agrónic API uses a different numeric user id. The user's own
        HAR confirms that this account uses Agrónic user id 13615.
        """
        await self.async_ensure_authenticated()

        # Keep the profile request because it verifies that the authenticated
        # account and organization are available, but do not interpret the
        # organization id as the Agrónic API user id.
        await self._request_url(
            "GET", f"{CORE_BASE_URL}/users/{self._username}/auth"
        )

        known_agronic_ids = {
            "ivanbenadresa": "13615",
        }
        user_id = known_agronic_ids.get(self._username.casefold())
        if not user_id:
            raise VeggaApiError(
                "No se pudo determinar automáticamente el identificador de usuario Agrónic"
            )

        data = await self._request("GET", f"/users/{user_id}/units")
        units = self._extract_list(
            data, ("content", "data", "units", "items", "results")
        )
        if not units:
            raise VeggaApiError("VEGGA no devolvió ningún controlador")
        return units


    async def get_unit_status(self) -> Any:
        """Return the controller's live status payload.

        VEGGA's programs and sectors endpoints mainly describe configuration.
        The unit endpoint with ``add=format`` is the live controller snapshot
        used by the web application.
        """
        if not self.device_id:
            raise VeggaApiError("No se ha seleccionado ningún controlador")
        return await self._request_url(
            "GET",
            f"{API_BASE_URL}/units/{self.device_id}",
            params={"add": "format"},
        )

    async def get_io_inputs_analog(self) -> Any:
        """Return live analogue input values from the A-5500."""
        if not self.device_id:
            raise VeggaApiError("No se ha seleccionado ningún controlador")
        return await self._request_url(
            "GET",
            f"{HISTORY_BASE_URL}/devices/A5500/{self.device_id}/io/inputs/ANALOG",
        )

    async def get_io_inputs_digital(self) -> Any:
        """Return live digital input values from the A-5500."""
        if not self.device_id:
            raise VeggaApiError("No se ha seleccionado ningún controlador")
        return await self._request_url(
            "GET",
            f"{HISTORY_BASE_URL}/devices/A5500/{self.device_id}/io/inputs/DIGITAL",
        )

    async def get_io_outputs_digital(self) -> Any:
        """Return live digital output values from the A-5500."""
        if not self.device_id:
            raise VeggaApiError("No se ha seleccionado ningún controlador")
        return await self._request_url(
            "GET",
            f"{HISTORY_BASE_URL}/devices/A5500/{self.device_id}/io/outputs/DIGITAL",
        )

    async def get_analog_sensors(self) -> list[dict[str, Any]]:
        """Return configured analogue sensors, including their live value."""
        if not self.device_id:
            raise VeggaApiError("No se ha seleccionado ningún controlador")
        data = await self._request_url(
            "GET",
            f"{API_BASE_URL}/units/{self.device_id}/analogs",
            params={"page": 1, "limit": 120},
        )
        return self._extract_nested_list(
            data, ("content", "analogs", "data", "items", "results")
        )

    async def get_analog_formats(self) -> list[dict[str, Any]]:
        """Return the decimal and unit definitions used by analogue sensors."""
        if not self.device_id:
            raise VeggaApiError("No se ha seleccionado ningún controlador")
        data = await self._request(
            "GET", f"/units/{self.device_id}/analogs/formatsview"
        )
        return self._extract_nested_list(
            data, ("content", "formats", "data", "items", "results")
        )

    async def get_meters(self) -> list[dict[str, Any]]:
        """Return controller flow meters and their live readings."""
        if not self.device_id:
            raise VeggaApiError("No se ha seleccionado ningún controlador")
        data = await self._request_url(
            "GET",
            f"{API_BASE_URL}/units/{self.device_id}/meters",
            params={"operative": "false"},
        )
        return self._extract_nested_list(
            data, ("content", "meters", "data", "items", "results")
        )

    async def get_fertilizer_config(self) -> Any:
        """Return A-5500 fertilization sensor assignments."""
        if not self.device_id:
            raise VeggaApiError("No se ha seleccionado ningún controlador")
        return await self._request_url(
            "GET",
            f"{API_BASE_URL}/units/{self.device_id}/config",
            params=[("add", "fertilizer"), ("add", "agitators")],
        )

    async def get_programs(self) -> list[dict[str, Any]]:
        if not self.device_id:
            raise VeggaApiError("No se ha seleccionado ningún controlador")
        data = await self._request("GET", f"/units/{self.device_id}/programs")
        programs = self._extract_list(data, ("content", "data", "programs", "items"))
        if programs or isinstance(data, list):
            return programs
        raise VeggaApiError("Formato de programas no reconocido")

    @staticmethod
    def _extract_nested_list(data: Any, preferred_keys: tuple[str, ...]) -> list[dict[str, Any]]:
        """Find a list of dictionaries in nested VEGGA responses.

        Some Agrónic endpoints return the entity list several levels below
        ``data``/``content``. The previous shallow parser therefore returned an
        empty list even though the endpoint answered HTTP 200.
        """
        if isinstance(data, list):
            items = [item for item in data if isinstance(item, dict)]
            if items:
                return items
            for item in data:
                found = VeggaApi._extract_nested_list(item, preferred_keys)
                if found:
                    return found
            return []

        if not isinstance(data, dict):
            return []

        # Follow the known wrapper keys first to avoid selecting an unrelated
        # nested list such as permissions or metadata.
        for key in preferred_keys:
            if key in data:
                found = VeggaApi._extract_nested_list(data[key], preferred_keys)
                if found:
                    return found

        # Some responses are maps keyed by sector number.
        dict_values = [value for value in data.values() if isinstance(value, dict)]
        if dict_values and len(dict_values) == len(data):
            return dict_values

        for value in data.values():
            found = VeggaApi._extract_nested_list(value, preferred_keys)
            if found:
                return found
        return []

    async def get_irrigating_sectors(self) -> list[dict[str, Any]]:
        """Return the live sector data used by VEGGA while irrigation is active.

        The VEGGA frontend requests ``/units/{id}/sectors?irrigation=true``.
        On the A-5500 these objects expose runtime fields such as ``xProgramN``.
        An empty or changed response is treated as no active irrigation so it
        never prevents the rest of the integration from loading.
        """
        if not self.device_id:
            raise VeggaApiError("No se ha seleccionado ningún controlador")
        data = await self._request_url(
            "GET",
            f"{API_BASE_URL}/units/{self.device_id}/sectors",
            params={"irrigation": "true"},
        )
        sectors = self._extract_nested_list(
            data, ("sectors", "content", "data", "items", "results", "value")
        )
        if sectors or isinstance(data, list):
            return [dict(item) for item in sectors]
        return []

    async def get_sectors(self) -> list[dict[str, Any]]:
        """Return irrigation sectors configured in the controller."""
        if not self.device_id:
            raise VeggaApiError("No se ha seleccionado ningún controlador")
        data = await self._request("GET", f"/units/{self.device_id}/sectors")
        sectors = self._extract_nested_list(
            data, ("sectors", "content", "data", "items", "results", "value")
        )
        if sectors:
            # The Agrónic endpoint may expose database identifiers (for example 30)
            # that are not the controller sector number used by history/manual calls.
            # VEGGA itself addresses sectors by their position: 1, 2, 3, ...
            normalized: list[dict[str, Any]] = []
            for agronic_number, sector_data in enumerate(sectors, start=1):
                item = dict(sector_data)
                item["_agronic_number"] = agronic_number
                normalized.append(item)
            return normalized

        # Do not make the complete integration unavailable when VEGGA changes
        # only the sector response format. Programs continue working and the
        # log contains enough information for a future adjustment.
        shape = list(data.keys()) if isinstance(data, dict) else type(data).__name__
        _LOGGER.warning("VEGGA returned no parseable sectors; response shape=%s", shape)
        return []


    @staticmethod
    def _looks_like_history_record(item: dict[str, Any]) -> bool:
        keys = {str(key).casefold() for key in item}
        has_sector = bool(keys & {
            "sector", "sectorid", "sector_id", "sectornumber", "sector_number",
            "sectorname", "sector_name", "name", "nombre"
        })
        has_measurement = bool(keys & {
            "volume", "volumen", "water", "watervolume", "irrigationvolume",
            "time", "tiempo", "duration", "durationseconds", "irrigationtime",
            "from", "to", "start", "end", "startdate", "enddate",
            "date", "fecha"
        })
        return has_sector and has_measurement

    @staticmethod
    def _extract_history_records(data: Any) -> list[dict[str, Any]]:
        """Recursively locate sector-history rows without depending on one wrapper."""
        found: list[dict[str, Any]] = []

        def walk(value: Any) -> None:
            if isinstance(value, list):
                dict_items = [item for item in value if isinstance(item, dict)]
                record_items = [item for item in dict_items if VeggaApi._looks_like_history_record(item)]
                if record_items:
                    found.extend(record_items)
                    return
                for item in value:
                    walk(item)
                return
            if isinstance(value, dict):
                if VeggaApi._looks_like_history_record(value):
                    found.append(value)
                    return
                for key in ("content", "data", "items", "results", "records", "history", "values", "rows"):
                    if key in value:
                        walk(value[key])
                if not found:
                    for child in value.values():
                        walk(child)

        walk(data)
        # Remove duplicate rows that may have been reached through wrapper aliases.
        unique: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in found:
            marker = json.dumps(item, sort_keys=True, default=str)
            if marker not in seen:
                seen.add(marker)
                unique.append(item)
        return unique

    @staticmethod
    def _history_record_sector(record: dict[str, Any]) -> int | None:
        lowered = {str(key).casefold(): value for key, value in record.items()}
        for key in ("sector", "sectorid", "sector_id", "sectornumber", "sector_number", "number"):
            value = lowered.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.strip().isdigit():
                return int(value.strip())
        return None

    async def get_sector_history(
        self,
        from_date: date,
        to_date: date,
        *,
        sector: int | None = None,
        grouping: str = "DAY",
        page_number: int = 1,
        page_size: int = 2000,
    ) -> list[dict[str, Any]]:
        """Return historical irrigation rows for all sectors or one sector."""
        if not self.device_id:
            raise VeggaApiError("No se ha seleccionado ningún controlador")
        params: dict[str, Any] = {
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "grouping": grouping,
            "pageNumber": page_number,
            "pageSize": page_size,
        }
        if sector is not None:
            params["sector"] = sector
        url = f"{HISTORY_BASE_URL}/devices/A5500/{self.device_id}/history/sectors"
        self.history_debug = {
            "url": url,
            "params": dict(params),
            "sector_requested": sector,
            "page_number_requested": page_number,
        }
        data = await self._request_url("GET", url, params=params)

        # Keep a small, token-free diagnostic sample visible in Home Assistant.
        # The HAR does not include the JSON response body, so this lets us see
        # VEGGA's real field names without exposing credentials.
        if isinstance(data, dict):
            top_keys = list(data.keys())[:30]
        else:
            top_keys = [type(data).__name__]

        def _sample(value: Any, depth: int = 0) -> Any:
            if depth >= 4:
                return f"<{type(value).__name__}>"
            if isinstance(value, dict):
                return {str(k): _sample(v, depth + 1) for k, v in list(value.items())[:20]}
            if isinstance(value, list):
                return [_sample(v, depth + 1) for v in value[:2]]
            if isinstance(value, str):
                return value[:200]
            return value

        self.history_debug.update({
            "top_level_keys": top_keys,
            "response_sample": _sample(data),
        })

        records = self._extract_history_records(data)

        # The history service uses a pageable response. Its row field names can
        # differ from the older Agrónic API, so fall back to the first nested
        # list of dictionaries instead of discarding a valid HTTP 200 response.
        if not records:
            records = self._extract_nested_list(
                data, ("content", "items", "results", "records", "history", "data", "rows")
            )

        # When a single sector is requested, some responses omit the sector
        # number from every row because it is already present in the query. Add
        # it locally so the analysis can associate each row with its entity.
        if sector is not None:
            normalized: list[dict[str, Any]] = []
            for record in records:
                item = dict(record)
                if self._history_record_sector(item) is None:
                    item["sector"] = sector
                normalized.append(item)
            records = normalized

        self.history_debug["parsed_record_count"] = len(records)
        if records:
            self.history_debug["first_record"] = _sample(records[0])

        if not records:
            shape = list(data.keys()) if isinstance(data, dict) else type(data).__name__
            _LOGGER.warning(
                "VEGGA returned no parseable sector history for sector=%s; response shape=%s",
                sector,
                shape,
            )
        return records

    async def manual_action(self, action: int, parameter1: int) -> Any:
        if not self.device_id:
            raise VeggaApiError("No se ha seleccionado ningún controlador")
        payload = {
            "type": 6,
            "deviceId": self.device_id,
            "action": action,
            "parameter1": parameter1,
        }
        return await self._request(
            "POST", f"/units/{self.device_id}/manual", json_data=payload
        )

    async def start_program(self, program_number: int) -> Any:
        return await self.manual_action(4, program_number - 1)

    async def stop_program(self, program_number: int) -> Any:
        return await self.manual_action(5, program_number - 1)

    async def start_sector(self, sector_number: int) -> Any:
        """Start a sector manually. HAR: action 9, zero-based parameter1."""
        return await self.manual_action(9, sector_number - 1)

    async def stop_sector(self, sector_number: int) -> Any:
        """Force a sector to manual stop. HAR: action 8, zero-based parameter1."""
        return await self.manual_action(8, sector_number - 1)

    async def automatic_sector(self, sector_number: int) -> Any:
        """Return a sector to automatic program control.

        Captured from the VEGGA web application: action 10 with a zero-based
        sector number in ``parameter1``.
        """
        return await self.manual_action(10, sector_number - 1)
