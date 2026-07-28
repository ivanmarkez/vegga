from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession

from .const import API_BASE_URL, CLIENT_ID, CORE_BASE_URL, LOGIN_URL, OAUTH_SCOPE

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
                timeout=20,
            ) as response:
                _LOGGER.debug("VEGGA API response %s %s -> HTTP %s", method, url, response.status)
                if response.status in (401, 403):
                    if retry_auth:
                        await self.async_ensure_authenticated(force=True)
                        return await self._request_url(
                            method,
                            url,
                            json_data=json_data,
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

    async def get_programs(self) -> list[dict[str, Any]]:
        if not self.device_id:
            raise VeggaApiError("No se ha seleccionado ningún controlador")
        data = await self._request("GET", f"/units/{self.device_id}/programs")
        programs = self._extract_list(data, ("content", "data", "programs", "items"))
        if programs or isinstance(data, list):
            return programs
        raise VeggaApiError("Formato de programas no reconocido")

    async def get_sectors(self) -> list[dict[str, Any]]:
        """Return irrigation sectors configured in the controller."""
        if not self.device_id:
            raise VeggaApiError("No se ha seleccionado ningún controlador")
        data = await self._request("GET", f"/units/{self.device_id}/sectors")
        sectors = self._extract_list(
            data, ("content", "data", "sectors", "items", "results")
        )
        if sectors or isinstance(data, list):
            return sectors
        raise VeggaApiError("Formato de sectores no reconocido")

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
        """Stop a sector manually. HAR: action 8, zero-based parameter1."""
        return await self.manual_action(8, sector_number - 1)
