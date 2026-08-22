import os
from dataclasses import dataclass

import httpx


class DevinAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class DevinConfig:
    api_key: str
    org_id: str
    repo: str
    repo_ref: str
    devin_mode: str
    max_acu_limit: int
    poll_interval: float
    run_timeout: float

    @classmethod
    def from_environment(cls) -> "DevinConfig | None":
        api_key = os.environ.get("DEVIN_API_KEY", "")
        org_id = os.environ.get("DEVIN_ORG_ID", "")
        if not api_key or api_key.startswith("apk_") or not org_id.startswith("org-"):
            return None
        return cls(
            api_key=api_key,
            org_id=org_id,
            repo=os.environ.get(
                "BIO_DASHBOARD_DEVIN_REPO",
                "anirudh027/ehl-cognition-2026",
            ),
            repo_ref=os.environ.get("BIO_DASHBOARD_DEVIN_REPO_REF", "main"),
            devin_mode=os.environ.get("BIO_DASHBOARD_DEVIN_MODE", "normal"),
            max_acu_limit=int(os.environ.get("BIO_DASHBOARD_DEVIN_MAX_ACU", "2")),
            poll_interval=float(os.environ.get("BIO_DASHBOARD_DEVIN_POLL_INTERVAL", "4")),
            run_timeout=float(os.environ.get("BIO_DASHBOARD_DEVIN_TIMEOUT", "1800")),
        )


class DevinClient:
    def __init__(
        self,
        config: DevinConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport
        self.base_url = "https://api.devin.ai"

    async def create_session(
        self,
        *,
        prompt: str,
        title: str,
        structured_output_schema: dict[str, object],
    ) -> dict[str, object]:
        return await self._request(
            "POST",
            f"/v3/organizations/{self.config.org_id}/sessions",
            json={
                "prompt": prompt,
                "title": title,
                "repos": [self.config.repo],
                "devin_mode": self.config.devin_mode,
                "max_acu_limit": self.config.max_acu_limit,
                "resumable": True,
                "structured_output_schema": structured_output_schema,
                "structured_output_required": True,
            },
        )

    async def get_session(self, session_id: str) -> dict[str, object]:
        return await self._request(
            "GET",
            f"/v3/organizations/{self.config.org_id}/sessions/{self._devin_id(session_id)}",
        )

    async def list_messages(self, session_id: str) -> list[dict[str, object]]:
        payload = await self._request(
            "GET",
            (
                f"/v3/organizations/{self.config.org_id}/sessions/"
                f"{self._devin_id(session_id)}/messages"
            ),
        )
        items = payload.get("items")
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict)]

    async def send_message(self, session_id: str, message: str) -> dict[str, object]:
        return await self._request(
            "POST",
            (
                f"/v3/organizations/{self.config.org_id}/sessions/"
                f"{self._devin_id(session_id)}/messages"
            ),
            json={"message": message},
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, object] | None = None,
    ) -> dict[str, object]:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=30,
            transport=self.transport,
        ) as client:
            response = await client.request(method, path, json=json)
        if response.is_error:
            try:
                detail = str(response.json().get("detail", response.reason_phrase))
            except (ValueError, AttributeError):
                detail = response.reason_phrase
            raise DevinAPIError(f"Devin API returned {response.status_code}: {detail}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise DevinAPIError("Devin API returned an unexpected response.")
        return payload

    def _devin_id(self, session_id: str) -> str:
        return session_id if session_id.startswith("devin-") else f"devin-{session_id}"
