class MachineError(Exception):
    pass


class MachineGone(MachineError):
    """Machine was deleted or is in destroyed state."""
    pass


class ExecutionFailed(MachineError):
    def __init__(self, status: str, error_code: str, error_message: str) -> None:
        self.status = status
        self.error_code = error_code
        self.error_message = error_message
        super().__init__(f"{status}: {error_code}: {error_message}")


class WakeTimeout(MachineError):
    pass


class PatchFailed(MachineError):
    pass
