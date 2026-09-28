"""Output helpers shared by the CLI commands.

Contract (relied on by programs that drive `snow -f json ...`):

* Results go to stdout. In json mode stdout carries exactly one JSON
  document per invocation, success or failure.
* Diagnostics (login progress, prompts, warnings) go to stderr.
* Error documents always contain an ``"error"`` code and a ``"message"``.
* The process exits non-zero on any error (see the EXIT_* constants).
"""
import json
import sys

EXIT_OK = 0
EXIT_ERROR = 1           # ticket not found, ServiceNow API error, update rejected, ...
EXIT_USAGE = 2           # bad command line (click's own convention)
EXIT_LOGIN_REQUIRED = 3  # a human has to log in (2FA / credentials / expired session)


class CommandFailed(Exception):
    """Raised by command code to stop with an error document and exit code."""

    def __init__(self, error, message, exit_code=EXIT_ERROR, extra=None):
        super().__init__(message)
        self.error = error
        self.message = message
        self.exit_code = exit_code
        self.extra = extra or {}


def diag(*args, **kwargs):
    """Print a diagnostic / progress message to stderr."""
    kwargs.setdefault("file", sys.stderr)
    kwargs.setdefault("flush", True)
    print(*args, **kwargs)


def is_json(ctx):
    return ctx.get("format") == "json"


def emit_json(obj, **dumps_kwargs):
    """Write one JSON document to stdout."""
    dumps_kwargs.setdefault("indent", 4)
    sys.stdout.write(json.dumps(obj, **dumps_kwargs) + "\n")
    sys.stdout.flush()


def error_document(error, message, extra=None):
    doc = {"error": error, "message": message}
    if extra:
        for k, v in extra.items():
            doc.setdefault(k, v)
    return doc


def fail(ctx, error, message, exit_code=EXIT_ERROR, extra=None):
    """Report an error in the current output format.

    In CLI mode this exits the process with ``exit_code``. In library mode
    (``ctx["api"]`` is true, see util/api.py) it prints nothing and returns
    None so existing callers keep getting a falsy result instead of
    SystemExit.
    """
    if ctx.get("api"):
        return None
    raise CommandFailed(error, message, exit_code, extra)


def report_failure(ctx, exc):
    """Print a CommandFailed in the right format (json -> stdout doc)."""
    if is_json(ctx):
        emit_json(error_document(exc.error, exc.message, exc.extra))
    else:
        # Text mode keeps the historical behaviour of printing the message
        # to stdout.
        print(exc.message)
