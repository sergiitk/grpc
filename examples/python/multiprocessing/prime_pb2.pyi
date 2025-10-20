from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class PrimeCandidate(_message.Message):
    __slots__ = ("candidate",)
    CANDIDATE_FIELD_NUMBER: _ClassVar[int]
    candidate: int
    def __init__(self, candidate: _Optional[int] = ...) -> None: ...

class Primality(_message.Message):
    __slots__ = ("isPrime",)
    ISPRIME_FIELD_NUMBER: _ClassVar[int]
    isPrime: bool
    def __init__(self, isPrime: bool = ...) -> None: ...
