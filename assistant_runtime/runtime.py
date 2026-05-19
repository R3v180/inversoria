from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class RuntimeContext:
    db: object
    exchange: object
    config: object
    language: str = "es"
    user_name: str = "User"
    focus_symbols: list[str] = field(default_factory=list)
    max_chars: int = 9000


@dataclass(order=True)
class ContextProvider:
    priority: int
    provider_id: str = field(compare=False)
    builder: Callable[[RuntimeContext], str] = field(compare=False)
    max_chars: int = field(default=1200, compare=False)


class ContextProviderRegistry:
    def __init__(self):
        self._providers: dict[str, ContextProvider] = {}

    def register(self, provider_id: str, builder: Callable[[RuntimeContext], str], priority: int = 100, max_chars: int = 1200):
        self._providers[provider_id] = ContextProvider(priority, provider_id, builder, max_chars)
        return self

    def build_sections(self, ctx: RuntimeContext) -> list[tuple[str, str]]:
        sections = []
        for provider in sorted(self._providers.values()):
            try:
                content = provider.builder(ctx)
            except Exception as exc:
                content = f"No disponible: {exc}"
            content = str(content or "").strip()
            if provider.max_chars and len(content) > provider.max_chars:
                content = content[: provider.max_chars].rstrip() + "\n...[recortado]"
            sections.append((provider.provider_id, content or "Sin datos."))
        return sections


class ActionRegistry:
    def __init__(self):
        self._actions: dict[str, dict] = {}

    def register(self, action_id: str, description: str, requires_confirmation: bool = True):
        self._actions[action_id] = {
            "id": action_id,
            "description": description,
            "requires_confirmation": requires_confirmation,
        }
        return self

    def describe(self) -> str:
        return "\n".join(
            f"- {item['id']}: {item['description']} (confirmación={item['requires_confirmation']})"
            for item in self._actions.values()
        )


def build_default_action_registry() -> ActionRegistry:
    return (
        ActionRegistry()
        .register("execute_order", "Crear una orden BUY/SELL pendiente para confirmación humana")
        .register("config_change", "Crear una propuesta de cambio de config pendiente de confirmación humana")
        .register("sell_dust", "Futuro flujo confirmable para vender dust")
        .register("open_review", "Futuro flujo para abrir una revisión guiada")
    )

