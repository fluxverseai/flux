"""Unit tests for flux_cli.lib.validation"""


from flux_cli.lib.validation import validate_flux_json, validate_name, validate_registry

# ---------------------------------------------------------------------------
# Name validation
# ---------------------------------------------------------------------------


class TestValidateName:
    def test_validate_name_valid(self):
        valid_names = ["my-mcp", "ab", "hello-world-123", "a1", "test-mcp-server"]
        for name in valid_names:
            ok, reason = validate_name(name)
            assert ok, f"Expected '{name}' to be valid, got: {reason}"

    def test_validate_name_too_short(self):
        ok, reason = validate_name("a")
        assert not ok
        assert "at least 2" in reason

    def test_validate_name_too_long(self):
        ok, reason = validate_name("a" * 51)
        assert not ok
        assert "at most 50" in reason

    def test_validate_name_uppercase_rejected(self):
        ok, reason = validate_name("My-MCP")
        assert not ok
        assert "lowercase" in reason

    def test_validate_name_special_chars_rejected(self):
        bad_names = ["my_mcp", "my.mcp", "my mcp", "my@mcp", "my/mcp"]
        for name in bad_names:
            ok, _ = validate_name(name)
            assert not ok, f"Expected '{name}' to be rejected"

    def test_validate_name_starts_with_hyphen_rejected(self):
        ok, _ = validate_name("-my-mcp")
        assert not ok

    def test_validate_name_ends_with_hyphen_rejected(self):
        ok, _ = validate_name("my-mcp-")
        assert not ok

    def test_validate_name_empty_string(self):
        ok, _ = validate_name("")
        assert not ok

    def test_validate_name_exactly_two_chars(self):
        ok, _ = validate_name("ab")
        assert ok

    def test_validate_name_exactly_fifty_chars(self):
        name = "a" + "b" * 48 + "c"
        assert len(name) == 50
        ok, _ = validate_name(name)
        assert ok


# ---------------------------------------------------------------------------
# Registry schema validation
# ---------------------------------------------------------------------------


class TestValidateRegistry:
    def test_valid_registry(self):
        data = {
            "version": "1.0.0",
            "mcp_definitions": {
                "my-mcp": {"type": "npm-package"},
            },
            "skill_definitions": {
                "my-skill": {"type": "github"},
            },
        }
        ok, errors = validate_registry(data)
        assert ok
        assert errors == []

    def test_missing_version(self):
        data = {"mcp_definitions": {}, "skill_definitions": {}}
        ok, errors = validate_registry(data)
        assert not ok
        assert any("version" in e for e in errors)

    def test_invalid_mcp_type(self):
        data = {
            "version": "1.0.0",
            "mcp_definitions": {
                "my-mcp": {"type": "invalid-type"},
            },
            "skill_definitions": {},
        }
        ok, errors = validate_registry(data)
        assert not ok
        assert any("invalid type" in e.lower() for e in errors)

    def test_invalid_mcp_name_in_registry(self):
        data = {
            "version": "1.0.0",
            "mcp_definitions": {
                "BAD_NAME": {"type": "npm-package"},
            },
            "skill_definitions": {},
        }
        ok, errors = validate_registry(data)
        assert not ok
        assert any("BAD_NAME" in e for e in errors)

    def test_empty_registry_valid(self):
        data = {"version": "1.0.0", "mcp_definitions": {}, "skill_definitions": {}}
        ok, errors = validate_registry(data)
        assert ok

    def test_not_a_dict(self):
        ok, errors = validate_registry([])  # type: ignore[arg-type]
        assert not ok
        assert any("object" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# flux.json schema validation
# ---------------------------------------------------------------------------


class TestValidateFluxJson:
    def test_valid_flux_json(self):
        data = {"name": "my-project", "mcps": ["memory"], "skills": []}
        ok, errors = validate_flux_json(data)
        assert ok

    def test_missing_name(self):
        data = {"mcps": [], "skills": []}
        ok, errors = validate_flux_json(data)
        assert not ok
        assert any("name" in e for e in errors)

    def test_mcps_not_list(self):
        data = {"name": "test", "mcps": "memory"}
        ok, errors = validate_flux_json(data)
        assert not ok
        assert any("mcps" in e for e in errors)

    def test_minimal_valid(self):
        data = {"name": "test"}
        ok, errors = validate_flux_json(data)
        assert ok
