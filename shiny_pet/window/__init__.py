from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .pet_window import PetWindow


def __getattr__(name: str) -> Any:
    if name == "PetWindow":
        from .pet_window import PetWindow

        return PetWindow
    raise AttributeError(name)

__all__ = ["PetWindow"]
