"""
Config Validator - Startup Configuration Validation
Nexira v12 Bug Resilience Foundation
Created by Xeeker & Claude - February 2026

Validates config on startup and catches problems before they
cause mysterious failures deep in the system.

Usage:
    from services.config_validator import ConfigValidator
    validator = ConfigValidator(config, error_logger)
    result = validator.validate()
    if not result['valid']:
        print("Config issues found:", result['issues'])
"""

from typing import Optional


class ConfigValidator:
    """
    Validates the loaded config dict against known requirements.
    Logs warnings/errors via ErrorLogger and returns a summary.
    """

    def __init__(self, config: dict, error_logger=None):
        self.config = config
        self.err = error_logger  # optional — works without it

    def validate(self) -> dict:
        """
        Run all validation checks.
        Returns {'valid': bool, 'issues': [...], 'warnings': [...]}
        """
        issues   = []  # blocking problems
        warnings = []  # non-blocking but worth knowing

        self._check_required_keys(issues)
        self._check_ai_section(issues, warnings)
        self._check_web_interface(issues, warnings)
        self._check_hardware(warnings)
        self._check_email_if_enabled(warnings)
        self._check_value_ranges(warnings)

        valid = len(issues) == 0

        # Log issues and warnings via ErrorLogger if available
        # Note: successful validations are NOT logged to avoid error_log noise.
        # Only actual problems (issues/warnings) are stored.
        if self.err:
            for msg in issues:
                self.err.log('config_validator', msg)
            for msg in warnings:
                self.err.warn('config_validator', msg)
            # Success is printed to console only, not stored in DB
        if valid and not warnings:
            print("✓ Config validation passed — all checks OK")
        elif valid:
            print(f"✓ Config validation passed with {len(warnings)} warning(s)")

        return {
            'valid':    valid,
            'issues':   issues,
            'warnings': warnings
        }

    # ── Checks ────────────────────────────────────────────────────────────

    def _check_required_keys(self, issues: list):
        """Ensure top-level required sections exist."""
        required = ['ai', 'hardware', 'memory', 'web_interface', 'monitoring']
        for key in required:
            if key not in self.config:
                issues.append(f"Missing required config section: '{key}'")

    def _check_ai_section(self, issues: list, warnings: list):
        ai = self.config.get('ai', {})
        if not ai.get('model'):
            issues.append("ai.model is empty — Ollama will not know which model to use")
        if not ai.get('ollama_url'):
            issues.append("ai.ollama_url is empty — cannot connect to Ollama")
        elif not ai['ollama_url'].startswith('http'):
            issues.append(f"ai.ollama_url looks invalid: '{ai['ollama_url']}' — should start with http://")

    def _check_web_interface(self, issues: list, warnings: list):
        web = self.config.get('web_interface', {})
        port = web.get('port')
        if port is None:
            issues.append("web_interface.port is missing")
        elif not isinstance(port, int) or port < 1024 or port > 65535:
            warnings.append(f"web_interface.port value '{port}' is unusual — expected 1024–65535")

    def _check_hardware(self, warnings: list):
        hw = self.config.get('hardware', {})
        threads = hw.get('num_threads', 0)
        if isinstance(threads, int) and threads < 1:
            warnings.append("hardware.num_threads is 0 — may cause performance issues")
        ctx = hw.get('context_window', 0)
        if isinstance(ctx, int) and ctx < 2048:
            warnings.append(f"hardware.context_window is {ctx} — very small, may truncate conversations")

    def _check_email_if_enabled(self, warnings: list):
        """Only validate email fields if email is actually enabled."""
        email = self.config.get('communication', {}).get('email', {})
        if not email.get('enabled'):
            return
        if not email.get('smtp_server'):
            warnings.append("Email is enabled but communication.email.smtp_server is empty")
        if not email.get('username'):
            warnings.append("Email is enabled but communication.email.username is empty")
        if not email.get('password'):
            warnings.append("Email is enabled but communication.email.password is empty")
        if not email.get('recipient') and not self.config.get('daily_email', {}).get('recipient'):
            warnings.append("Email is enabled but no recipient address is configured")

    def _check_value_ranges(self, warnings: list):
        mem = self.config.get('memory', {})
        short_term = mem.get('short_term_messages', 50)
        if isinstance(short_term, int) and short_term < 5:
            warnings.append(f"memory.short_term_messages is {short_term} — very low, Sygma will forget conversations quickly")

        personality = self.config.get('personality', {})
        speed = personality.get('evolution_speed', 0.02)
        if isinstance(speed, (int, float)) and speed > 0.5:
            warnings.append(f"personality.evolution_speed is {speed} — very high, personality may drift rapidly")
