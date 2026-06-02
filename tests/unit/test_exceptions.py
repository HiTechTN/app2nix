"""
Unit tests for app2nix/exceptions.py — exception hierarchy.
"""

import pytest

from app2nix.exceptions import (
    AnalysisError,
    App2NixError,
    GenerationError,
    UnsupportedFormatError,
    ValidationError,
)


class TestExceptionHierarchy:
    def test_app2nix_error_is_base_exception(self):
        assert issubclass(App2NixError, Exception)

    def test_analysis_error_inherits_app2nix(self):
        assert issubclass(AnalysisError, App2NixError)
        assert issubclass(AnalysisError, Exception)

    def test_unsupported_format_inherits_analysis(self):
        assert issubclass(UnsupportedFormatError, AnalysisError)
        assert issubclass(UnsupportedFormatError, App2NixError)

    def test_generation_error_inherits_app2nix(self):
        assert issubclass(GenerationError, App2NixError)

    def test_validation_error_inherits_app2nix(self):
        assert issubclass(ValidationError, App2NixError)


class TestExceptionMessages:
    def test_app2nix_error_message(self):
        exc = App2NixError("something broke")
        assert str(exc) == "something broke"

    def test_analysis_error_message(self):
        exc = AnalysisError("analysis failed")
        assert str(exc) == "analysis failed"

    def test_unsupported_format_message(self):
        exc = UnsupportedFormatError("format .xyz not supported")
        assert str(exc) == "format .xyz not supported"

    def test_generation_error_message(self):
        exc = GenerationError("template render failed")
        assert str(exc) == "template render failed"

    def test_validation_error_message(self):
        exc = ValidationError("invalid nix syntax")
        assert str(exc) == "invalid nix syntax"


class TestExceptionCatching:
    def test_catch_unsupported_as_analysis(self):
        with pytest.raises(AnalysisError):
            raise UnsupportedFormatError("nope")

    def test_catch_analysis_as_app2nix(self):
        with pytest.raises(App2NixError):
            raise AnalysisError("nope")

    def test_catch_generation_as_app2nix(self):
        with pytest.raises(App2NixError):
            raise GenerationError("nope")

    def test_catch_validation_as_app2nix(self):
        with pytest.raises(App2NixError):
            raise ValidationError("nope")
