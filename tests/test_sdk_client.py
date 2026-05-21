import pytest

from src.sdk import AuthenticationError, OrchestratorClient


class TestOrchestratorClientAuthSetup:
    def test_missing_api_key_fails_before_headers(self, monkeypatch):
        monkeypatch.delenv("AO_API_KEY", raising=False)

        with pytest.raises(AuthenticationError) as exc_info:
            OrchestratorClient(base_url="https://example.test")

        message = str(exc_info.value)
        assert "non-blank API key string is required" in message
        assert "Pass api_key or set AO_API_KEY" in message

    def test_blank_api_key_argument_fails(self, monkeypatch):
        monkeypatch.setenv("AO_API_KEY", "env-secret")

        with pytest.raises(AuthenticationError):
            OrchestratorClient(
                base_url="https://example.test",
                api_key="   ",
            )

    def test_blank_env_api_key_fails(self, monkeypatch):
        monkeypatch.setenv("AO_API_KEY", "\t  \n")

        with pytest.raises(AuthenticationError):
            OrchestratorClient(base_url="https://example.test")

    def test_non_string_api_key_argument_fails(self, monkeypatch):
        monkeypatch.setenv("AO_API_KEY", "env-secret")

        with pytest.raises(AuthenticationError) as exc_info:
            OrchestratorClient(
                base_url="https://example.test",
                api_key=123,
            )

        assert "non-blank API key string is required" in str(exc_info.value)

    def test_explicit_api_key_overrides_blank_env(self, monkeypatch):
        monkeypatch.setenv("AO_API_KEY", "   ")

        client = OrchestratorClient(
            base_url="https://example.test",
            api_key="explicit-secret",
        )

        assert client.api_key == "explicit-secret"

    def test_api_key_argument_builds_authorization_header(self, monkeypatch):
        captured = {}

        def fake_urlopen(req):
            captured["headers"] = dict(req.header_items())

            class FakeResponse:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, traceback):
                    return False

                def read(self):
                    return b'{"ok": true}'

            return FakeResponse()

        monkeypatch.setattr("src.sdk.client.urlopen", fake_urlopen)

        client = OrchestratorClient(
            base_url="https://example.test",
            api_key="  explicit-secret  ",
        )

        assert client.list_agents() == {"ok": True}
        assert captured["headers"]["Authorization"] == (
            "Bearer explicit-secret"
        )

    def test_env_api_key_builds_authorization_header(self, monkeypatch):
        captured = {}

        def fake_urlopen(req):
            captured["headers"] = dict(req.header_items())

            class FakeResponse:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, traceback):
                    return False

                def read(self):
                    return b'{"agents": []}'

            return FakeResponse()

        monkeypatch.setenv("AO_API_KEY", "env-secret")
        monkeypatch.setattr("src.sdk.client.urlopen", fake_urlopen)

        client = OrchestratorClient(base_url="https://example.test")

        assert client.list_agents() == {"agents": []}
        assert captured["headers"]["Authorization"] == "Bearer env-secret"
