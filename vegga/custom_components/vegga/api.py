from __future__ import annotations

from typing import Any

from aiohttp import ClientResponseError, ClientSession


class VeggaApiError(Exception):
    """Base VEGGA API error."""


class VeggaAuthError(VeggaApiError):
    """Authentication error."""


class VeggaApi:
    """Small async client for the VEGGA REST API."""

    def __init__(self, session: ClientSession, device_id: str, token: str) -> None:
        self._session = session
        self.device_id = str(device_id)
        self._token = token.strip()

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "Content-Type": "application/json;charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_data: dict[str, Any] | None = None,
    ) -> Any:
        url = f"https://vegga-prod.azure-api.net/agronic/api/v1{path}"
        try:
            async with self._session.request(
                method,
                url,
                headers=self.headers,
                json=json_data,
                timeout=20,
            ) as response:
                if response.status in (401, 403):
                    raise VeggaAuthError("Token no válido o caducado")
                response.raise_for_status()
                if response.content_type == "application/json":
                    return await response.json()
                return await response.text()
        except VeggaAuthError:
            raise
        except ClientResponseError as err:
            raise VeggaApiError(f"Error HTTP {err.status}") from err
        except Exception as err:
            raise VeggaApiError(str(err)) from err

    async def get_programs(self) -> list[dict[str, Any]]:
        data = await self._request(
            "GET", f"/units/{self.device_id}/programs"
        )
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("content", "data", "programs", "items"):
                value = data.get(key)
                if isinstance(value, list):
                    return value
        raise VeggaApiError("Formato de programas no reconocido")

    async def manual_action(self, action: int, parameter1: int) -> Any:
        payload = {
            "type": 6,
            "deviceId": self.device_id,
            "action": action,
            "parameter1": parameter1,
        }
        return await self._request(
            "POST",
            f"/units/{self.device_id}/manual",
            json_data=payload,
        )

    async def start_program(self, program_number: int) -> Any:
        return await self.manual_action(4, program_number - 1)

    async def stop_program(self, program_number: int) -> Any:
        return await self.manual_action(5, program_number - 1)
