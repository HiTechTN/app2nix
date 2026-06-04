class App2NixError(Exception):
    pass

class AnalysisError(App2NixError):
    pass

class UnsupportedFormatError(AnalysisError):
    pass

class GenerationError(App2NixError):
    pass

class ValidationError(App2NixError):
    pass
